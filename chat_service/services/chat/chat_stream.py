"""Streaming chat service: LangGraph stream -> protocol events.

Streams the same compiled graph as ``ChatService.ask`` (Checkpointer short-term
memory, Store long-term memory, HITL gate) but yields protocol events instead
of blocking for one final string.

Streaming mechanism
-------------------
Two stream modes are consumed together:

- ``custom`` — the agent node publishes each LLM chunk through LangGraph's
  ``get_stream_writer()``. This is the only reliable token-level channel:
  node-internal LLM tokens do not surface as ``on_chat_model_stream`` in
  ``astream_events``.
- ``messages`` — LangGraph's state updates, which carry ToolMessages (tool
  results) and the ``__interrupt__`` payload.

Both are required: ``custom`` alone has no node/tool/interrupt context, and
``messages`` alone only produces the aggregated final AIMessage.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from chat_service.services.chat.stream_events import (
    TOKEN_SCOPE_ALL,
    StreamEvent,
    StreamEventMapper,
)
from langchain_agent.app.graph import build_memory_agent_graph
from qa_service import llm_client

logger = logging.getLogger(__name__)

RECURSION_LIMIT = 25
STREAM_MODES = ["custom", "messages", "updates"]


def _absorb_updates(
    chunk: Any,
    state: Dict[str, Any],
    tool_messages: List[ToolMessage],
) -> Dict[str, Any]:
    """Merge one ``updates``-channel payload and collect its ToolMessages.

    The payload is a node-keyed state delta, e.g.
    ``{"tools": {"messages": [ToolMessage(...)]}}``; the ``__interrupt__`` key
    is run metadata and is not merged into state.

    Tool results are collected here rather than read from the final state
    because a checkpointed thread may hold ToolMessages from earlier turns,
    which would otherwise be re-sent on every subsequent request.
    """
    if not isinstance(chunk, dict):
        return state
    for key, value in chunk.items():
        if key == "__interrupt__" or not isinstance(value, dict):
            continue
        state.update(value)
        for message in value.get("messages", []) or []:
            if isinstance(message, ToolMessage):
                tool_messages.append(message)
    return state


def _read_final_state(graph: Any, config: Dict[str, Any]) -> Dict[str, Any]:
    """Read the run's final state from the checkpointer as a fallback."""
    try:
        snapshot = graph.get_state(config)
        return dict(snapshot.values or {})
    except Exception:  # noqa: BLE001 - diagnostics must never break the stream
        logger.debug("chat.stream.final_state_unavailable", exc_info=True)
        return {}


def _final_state_events(
    state: Dict[str, Any],
    mapper: StreamEventMapper,
    tool_messages: List[ToolMessage],
) -> List[StreamEvent]:
    """Derive tool_result and usage events for this run.

    ``tool_messages`` holds the ToolMessages produced by *this* run (collected
    from the updates channel); ``state`` supplies the final AIMessage, which
    carries the aggregated ``usage_metadata``.
    """
    events: List[StreamEvent] = []
    for message in tool_messages:
        content = message.content if isinstance(message.content, str) else str(message.content)
        mapper.note_tool_result(
            message.tool_call_id or "", message.name or "", content, "ok"
        )
        events.append(
            StreamEvent(
                "tool_result",
                {
                    "id": message.tool_call_id or "",
                    "name": message.name or "",
                    "status": "error" if message.status == "error" else "ok",
                    "content": content,
                },
            )
        )

    for message in reversed(state.get("messages", []) or []):
        usage = (getattr(message, "response_metadata", None) or {}).get(
            "usage_metadata"
        )
        if isinstance(usage, dict):
            mapper.usage.add(usage)
            break
    return events


class ChatStreamService:
    """Stream one chat turn as protocol events."""

    def __init__(self, memory_runtime: Any) -> None:
        self._memory_runtime = memory_runtime

    def _build_graph(self, llm: Optional[Any] = None) -> Any:
        return build_memory_agent_graph(
            llm=llm if llm is not None else llm_client.get_llm(),
            checkpointer=self._memory_runtime.checkpointer,
            store=self._memory_runtime.get_store(),
            streaming=True,
        )

    def _build_config(self, thread_id: str, user_id: Optional[str]) -> Dict[str, Any]:
        return {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id or "default-user",
            },
            "metadata": {
                "thread_id": thread_id,
                "user_id": user_id or "default-user",
                "entrypoint": "chat_service.api.chat.stream",
            },
            "tags": ["chat_service", "chat-stream"],
            "recursion_limit": RECURSION_LIMIT,
        }

    async def _run(
        self,
        graph: Any,
        inputs: Any,
        config: Dict[str, Any],
        thread_id: str,
        token_scope: str,
    ) -> AsyncIterator[StreamEvent]:
        """Drive one graph run, translating the stream into protocol events.

        Tool results and token usage are not part of the streaming payloads
        (LangGraph emits only the aggregated final state), so they are read
        from the run's final checkpoint state once the stream ends.
        """
        mapper = StreamEventMapper(thread_id=thread_id, token_scope=token_scope)
        interrupted = False
        final_state: Dict[str, Any] = {}
        tool_messages: List[ToolMessage] = []

        try:
            async for mode, chunk in graph.astream(
                inputs,
                config=config,
                stream_mode=STREAM_MODES,
            ):
                if mode == "custom":
                    events = mapper.map_custom(chunk)
                elif mode == "messages":
                    events = mapper.map_messages(chunk)
                elif mode == "updates":
                    events = mapper.map_updates(chunk)
                    final_state = _absorb_updates(chunk, final_state, tool_messages)
                else:
                    events = []
                for event in events:
                    if event.type == "interrupt":
                        interrupted = True
                    yield event
        except GraphRecursionError:
            logger.warning("chat.stream.recursion_limit thread_id=%s", thread_id)
            yield StreamEvent(
                "error",
                {"message": "请求步骤过多，已安全停止。", "code": "recursion_limit"},
            )
        except Exception as exc:  # noqa: BLE001 - surface provider errors to the UI
            logger.exception("chat.stream.failed thread_id=%s", thread_id)
            yield StreamEvent(
                "error",
                {"message": f"{type(exc).__name__}: {exc}", "code": "upstream"},
            )

        if not final_state:
            final_state = _read_final_state(graph, config)

        for event in mapper.flush_final_scope():
            yield event
        for event in _final_state_events(final_state, mapper, tool_messages):
            yield event
        if interrupted:
            yield StreamEvent(
                "done", {"usage": None, "finish_reason": "interrupt"}
            )
            return
        yield StreamEvent(
            "done",
            {
                "usage": mapper.usage.to_dict(),
                "finish_reason": "stop",
            },
        )

    async def stream_turn(
        self,
        question: str,
        thread_id: str,
        user_id: Optional[str] = None,
        token_scope: str = TOKEN_SCOPE_ALL,
        llm: Optional[Any] = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield protocol events for one question turn.

        Always terminates with a ``done`` event, so the frontend can
        unconditionally clear its loading state.
        """
        question = (question or "").strip()
        if not question:
            yield StreamEvent(
                "error", {"message": "Question must not be empty.", "code": "input"}
            )
            yield StreamEvent("done", {"usage": None, "finish_reason": "stop"})
            return

        graph = self._build_graph(llm=llm)
        config = self._build_config(thread_id, user_id)
        async for event in self._run(
            graph,
            {"messages": [HumanMessage(content=question)]},
            config,
            thread_id,
            token_scope,
        ):
            yield event

    async def stream_resume(
        self,
        thread_id: str,
        user_id: Optional[str] = None,
        resume_value: Any = True,
        token_scope: str = TOKEN_SCOPE_ALL,
    ) -> AsyncIterator[StreamEvent]:
        """Resume an interrupted turn via ``Command(resume=...)``.

        Uses the same checkpointer, so the graph continues from the exact
        interrupt point without repeating the LLM call that requested the tool.
        """
        graph = self._build_graph()
        config = self._build_config(thread_id, user_id)
        async for event in self._run(
            graph,
            Command(resume=resume_value),
            config,
            thread_id,
            token_scope,
        ):
            yield event


async def sse_stream(events: AsyncIterator[StreamEvent]) -> AsyncIterator[str]:
    """Convert protocol events into SSE frames."""
    async for event in events:
        yield event.to_sse()
