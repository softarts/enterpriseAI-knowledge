"""LangGraph workflow: short-term checkpointer memory + long-term memory agent.

Graph assembly only. Long-term memory logic (store factory, retrieval, write,
structured extraction, tool creation) lives in app/long_memory.py and is
imported here; short-term history stays owned by the Checkpointer.
"""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.config import get_stream_writer
from langgraph.store.base import BaseStore
from langgraph.types import interrupt

from . import config as app_config
from .long_memory import (
    create_memory_store,
    create_search_memory_tool,
    extract_and_save_memory,
)
from .long_memory_prompts import MemoryExtraction
from .prompts import BASE_SYSTEM_PROMPT
from .state import MemoryGraphState
from .tool_layer import calculator, create_web_search_tool, get_current_time

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d - %(message)s"
)


def chunk_text(chunk: Any) -> str:
    """Extract plain text from a streamed LLM chunk (content may be a list)."""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return ""


def _normalize_tool_call(raw: Any) -> Optional[Dict[str, Any]]:
    """Normalize a streamed tool-call fragment into {id, name, args}.

    Streamed fragments arrive either as ``tool_call_chunks`` dicts — whose
    ``args`` is a *partial JSON string* that must be parsed and merged — or as
    fully-parsed ``tool_calls`` entries whose ``args`` is already a dict. Both
    forms are normalized here so the aggregated AIMessage is valid.
    """
    if isinstance(raw, dict):
        name = raw.get("name")
        if not name:
            # Argument-only continuation fragment; the accumulated AIMessage
            # from langchain-core already merges these.
            return None
        args = raw.get("args")
        if isinstance(args, str):
            args = _parse_tool_args(args)
        return {
            "id": str(raw.get("id") or ""),
            "name": str(name),
            "args": args if isinstance(args, dict) else {},
        }
    name = getattr(raw, "name", None)
    if not name:
        return None
    args = getattr(raw, "args", {})
    return {
        "id": str(getattr(raw, "id", "") or ""),
        "name": str(name),
        "args": args if isinstance(args, dict) else {},
    }


def _parse_tool_args(raw: str) -> Dict[str, Any]:
    """Parse a tool-call argument fragment, tolerating partial JSON."""
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Partial fragment mid-stream: keep the raw text under a diagnostic key
        # rather than dropping the call entirely.
        return {"__raw_args__": text}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _build_request_payload_preview(
    llm: BaseChatModel,
    bound: Any,
    messages: List[BaseMessage],
) -> Optional[Dict[str, Any]]:
    """Best-effort reconstruction of the outbound chat-completion payload.

    Intended for debugging only: it never raises, and returns None when the
    provider does not expose ``_get_request_payload`` (e.g. tests use a mock
    chat model). ``bound`` is the RunnableBinding produced by ``bind_tools``;
    its ``kwargs`` carry the exact ``tools`` argument sent to the provider.
    """
    builder = getattr(llm, "_get_request_payload", None)
    if builder is None:
        return None
    bound_kwargs = getattr(bound, "kwargs", None) or {}
    try:
        return builder(messages, **dict(bound_kwargs))
    except Exception:
        logger.warning("memory.agent.payload.preview_failed", exc_info=True)
        return None


def create_agent_node(
    llm: BaseChatModel,
    system_prompt: Optional[str] = None,
    tools: Optional[Sequence[BaseTool]] = None,
):
    """Create an agent that adds system instructions without storing them.

    Tools are bound to the LLM here; whether to call them is decided by the
    model inside the tool-calling loop, never by pre-retrieval in a pipeline.
    """
    system_content = BASE_SYSTEM_PROMPT
    if system_prompt:
        system_content = f"{BASE_SYSTEM_PROMPT}\n\n{system_prompt}"
    llm_with_tools = llm.bind_tools(list(tools)) if tools else llm

    def agent(
        state: MemoryGraphState,
        config: RunnableConfig,
    ) -> Dict[str, Any]:
        messages = state["messages"]
        configurable = config.get("configurable", {})
        logger.info(
            "memory.agent.invoke thread_id=%s message_count=%d message_types=%s",
            configurable.get("thread_id"),
            len(messages),
            [getattr(message, "type", type(message).__name__) for message in messages],
        )
        system = SystemMessage(content=system_content)
        outbound = [system] + messages
        payload = _build_request_payload_preview(llm, llm_with_tools, outbound)
        if payload is not None:
            logger.info(
                "memory.agent.request_payload thread_id=%s payload=%s",
                configurable.get("thread_id"),
                json.dumps(payload, ensure_ascii=False, default=str),
            )
        response = llm_with_tools.invoke(outbound, config=config)
        logger.info(
            "memory.agent.completed thread_id=%s response_type=%s tool_calls=%d",
            configurable.get("thread_id"),
            getattr(response, "type", type(response).__name__),
            len(getattr(response, "tool_calls", None) or []),
        )
        return {"messages": [response]}

    return agent


def create_async_agent_node(
    llm: BaseChatModel,
    system_prompt: Optional[str] = None,
    tools: Optional[Sequence[BaseTool]] = None,
):
    """Async agent node that streams the LLM response token by token.

    Each LLM chunk is published through LangGraph's custom stream writer
    (``get_stream_writer()``) so ``astream(stream_mode="custom")`` surfaces
    real token-level output. Chunks are also aggregated locally so the node
    returns one AIMessage, identical in shape to the sync node's return value.
    """

    system_content = BASE_SYSTEM_PROMPT
    if system_prompt:
        system_content = f"{BASE_SYSTEM_PROMPT}\n\n{system_prompt}"
    llm_with_tools = llm.bind_tools(list(tools)) if tools else llm

    async def agent(
        state: MemoryGraphState,
        config: RunnableConfig,
    ) -> Dict[str, Any]:
        messages = state["messages"]
        configurable = config.get("configurable", {})
        writer = get_stream_writer()
        logger.info(
            "memory.agent.astream thread_id=%s message_count=%d",
            configurable.get("thread_id"),
            len(messages),
        )
        outbound = [SystemMessage(content=system_content)] + list(messages)

        parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        seen_call_ids: set = set()
        usage_metadata: Optional[Dict[str, int]] = None
        async for chunk in llm_with_tools.astream(outbound, config=config):
            if not isinstance(chunk, AIMessage):
                continue
            text = chunk_text(chunk)
            # A streamed call appears both as tool_call_chunks (raw fragments)
            # and tool_calls (parsed); both are inspected and de-duplicated by
            # id so the aggregated AIMessage carries exactly one entry per call.
            fragments = list(chunk.tool_call_chunks or []) + list(chunk.tool_calls or [])
            if fragments:
                for raw in fragments:
                    call = _normalize_tool_call(raw)
                    if not call:
                        continue
                    key = call["id"] or f"{call['name']}:{len(tool_calls)}"
                    if key in seen_call_ids:
                        continue
                    seen_call_ids.add(key)
                    tool_calls.append(call)
                    writer({"kind": "tool_call", **call})
            elif text:
                parts.append(text)
                writer({"kind": "token", "text": text})
            chunk_usage = (chunk.response_metadata or {}).get("usage_metadata")
            if isinstance(chunk_usage, dict):
                usage_metadata = chunk_usage

        response = AIMessage(content="".join(parts), tool_calls=tool_calls)
        if usage_metadata:
            response.response_metadata = {"usage_metadata": usage_metadata}
        logger.info(
            "memory.agent.astream.completed thread_id=%s answer_chars=%d tool_calls=%d",
            configurable.get("thread_id"),
            len(response.content),
            len(tool_calls),
        )
        return {"messages": [response]}

    return agent


def should_continue(state: MemoryGraphState) -> str:
    """Route to tools while the last AI message requests tool calls."""
    # print("=" * 30, "should_continue stack trace", "=" * 30)
    # print("".join(traceback.format_stack()[:-1]))
    logger.info("should_continue Route to tools while the last AI message requests tool calls.")

    last_message = state["messages"][-1]
    print("should_continue => check last_message: %s\n", last_message)
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "update_memory"


# Tools that touch the open internet and therefore require explicit user
# confirmation (HITL) before execution.
HITL_TOOLS = {"web_search"}


def _needs_confirmation(tool_name: str) -> bool:
    """Whether a tool call must pause for human confirmation.

    ``web_search`` is auto-executed by default (``WEB_SEARCH_AUTO_EXECUTE``);
    set that switch to false to restore the manual confirm prompt for it.
    """
    if tool_name not in HITL_TOOLS:
        return False
    if tool_name == "web_search" and app_config.WEB_SEARCH_AUTO_EXECUTE:
        return False
    return True


def hitl_gate_node(state: MemoryGraphState, config: RunnableConfig) -> Dict[str, Any]:
    """Pause for human confirmation before running sensitive tools.

    Only interrupts when the pending tool call is in ``HITL_TOOLS`` and is not
    exempted by ``_needs_confirmation`` (e.g. auto-executed web_search);
    otherwise passes straight through so the agent loop is not slowed down.
    Resuming the thread with ``Command(resume=...)`` lets the tool run.
    """
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    pending = [c for c in tool_calls if _needs_confirmation(c.get("name"))]
    if not app_config.HITL_ENABLED or not pending:
        return {}
    names = ", ".join(c["name"] for c in pending)
    answer = interrupt(
        {
            "question": f"即将调用外部工具 {names}，是否继续？",
            "tools": [{"id": c["id"], "name": c["name"], "args": c.get("args", {})} for c in pending],
        }
    )
    # resume value is intentionally unused beyond unblocking; LangGraph re-runs
    # this node on resume, and the approved tool call proceeds via `tools`.
    logger.info("hitl_gate resumed answer=%s", answer)
    return {}


def route_after_hitl(state: MemoryGraphState) -> str:
    """After the HITL gate, always continue to the tools node."""
    return "tools"


def create_update_memory_node(llm: BaseChatModel):
    """Create the post-answer long-term memory write node.

    The node runs after the agent produced its final answer; it is not a tool
    and is never visible to the LLM. Extraction uses structured output, and
    any failure is logged without interrupting the answered turn.
    """
    extraction_llm = llm.with_structured_output(MemoryExtraction)

    def update_memory(
        state: MemoryGraphState,
        config: RunnableConfig,
        *,
        store: BaseStore,
    ) -> Dict[str, Any]:
        logger.info("*** update_memory. ***")
        
        configurable = config.get("configurable", {})
        user_id = configurable.get("user_id")
        thread_id = configurable.get("thread_id")
        if not user_id:
            logger.info(
                "memory.longterm.update.skip thread_id=%s reason=no_user_id",
                thread_id,
            )
            return {}
        latest_human: Optional[HumanMessage] = None
        for message in reversed(state["messages"]):
            if isinstance(message, HumanMessage):
                latest_human = message
                break
        if latest_human is None or not str(latest_human.content).strip():
            return {}
        try:
            saved = extract_and_save_memory(
                store=store,
                user_id=user_id,
                extraction_llm=extraction_llm,
                extraction_input=str(latest_human.content),
                thread_id=thread_id,
                message_id=latest_human.id,
            )
            logger.info(
                "memory.longterm.update.completed thread_id=%s user_id=%s saved=%s",
                thread_id,
                user_id,
                saved,
            )
        except Exception:
            logger.warning(
                "memory.longterm.update.failed thread_id=%s user_id=%s",
                thread_id,
                user_id,
                exc_info=True,
            )
        return {}

    return update_memory


def build_memory_agent_graph(
    llm: Optional[BaseChatModel] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    system_prompt: Optional[str] = None,
    store: Optional[BaseStore] = None,
    tools: Optional[List[BaseTool]] = None,
    streaming: bool = False,
) -> CompiledStateGraph:
    """Build the agent graph with checkpointer (short-term) and store (V2).

    Control flow: START -> agent; agent loops with the tools node while the
    model requests tool calls; once the model answers, update_memory runs the
    structured long-term memory extraction, then END.

    ``streaming=True`` swaps the agent node for its async variant so
    ``astream_events`` surfaces token-level ``on_chat_model_stream`` events.
    The sync ``invoke`` path is unchanged.
    """
    active_llm = llm or app_config.get_chat_model()
    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()
    active_store = store if store is not None else create_memory_store()
    active_tools: List[BaseTool] = (
        list(tools)
        if tools is not None
        else [
            create_search_memory_tool(default_top_k=app_config.MEMORY_TOP_K),
            create_web_search_tool(),
            calculator,
            get_current_time,
        ]
    )

    agent_node = (
        create_async_agent_node(active_llm, system_prompt=system_prompt, tools=active_tools)
        if streaming
        else create_agent_node(
            active_llm, system_prompt=system_prompt, tools=active_tools
        )
    )

    workflow = StateGraph(MemoryGraphState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("hitl_gate", hitl_gate_node)
    workflow.add_node("tools", ToolNode(active_tools))
    workflow.add_node("update_memory", create_update_memory_node(active_llm))
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "hitl_gate", "update_memory": "update_memory"},
    )
    workflow.add_conditional_edges("hitl_gate", route_after_hitl, {"tools": "tools"})
    workflow.add_edge("tools", "agent")
    workflow.add_edge("update_memory", END)

    return workflow.compile(checkpointer=active_checkpointer, store=active_store)
