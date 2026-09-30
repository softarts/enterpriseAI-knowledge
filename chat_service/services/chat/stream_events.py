"""SSE event protocol for POST /api/chat/stream.

Wire format: one JSON object per SSE ``data:`` line, terminated by a blank line.

    data: {"type":"token","text":"你好"}

Event types
-----------
token        {"type":"token","text":str,"turn":int}
tool_call    {"type":"tool_call","id":str,"name":str,"args":object}
tool_result  {"type":"tool_result","id":str,"name":str,"status":"ok"|"error","content":str}
node_start   {"type":"node_start","node":str}
interrupt    {"type":"interrupt","thread_id":str,"question":str,"resume_key":str,"tools":[...]}
done         {"type":"done","usage":{"input_tokens":int,"output_tokens":int}|null,
              "finish_reason":"stop"|"interrupt"}
error        {"type":"error","message":str,"code":str}

Sources
-------
``map_custom``   consumes ``stream_mode="custom"`` payloads written by the
                 agent node (tokens and tool calls).
``map_messages`` consumes ``stream_mode="messages"`` state updates, which
                 carry ToolMessages (tool results), node names and the
                 ``__interrupt__`` payload.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

TOKEN_SCOPE_FINAL = "final"
TOKEN_SCOPE_ALL = "all"

# Internal marker the agent node writes for a tool-call chunk.
CUSTOM_TOKEN = "token"
CUSTOM_TOOL_CALL = "tool_call"


@dataclass
class StreamEvent:
    """One protocol event; ``type`` drives frontend routing."""

    type: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        payload = json.dumps({"type": self.type, **self.data}, ensure_ascii=False)
        return f"data: {payload}\n\n"


@dataclass
class TokenUsage:
    """Accumulated token usage across every LLM call in one request."""

    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, usage: Dict[str, Any]) -> None:
        self.input_tokens += int(
            usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
        )
        self.output_tokens += int(
            usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
        )

    def to_dict(self) -> Dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


class StreamEventMapper:
    """Translate LangGraph stream chunks into protocol events.

    Responsibilities the raw stream does not handle:

    - **node_start de-duplication**: LangGraph repeats node updates across
      supersteps, so only the first sighting of a node is forwarded.
    - **token scoping**: with ``token_scope="final"`` the first agent round is
      buffered and only emitted if no tool call follows; otherwise tokens are
      forwarded immediately.
    - **usage aggregation**: ``usage_metadata`` from the final AIMessage is
      summed into the ``done`` event.
    - **interrupt synthesis**: LangGraph has no dedicated interrupt event; the
      ``__interrupt__`` payload arrives on the messages channel.
    """

    def __init__(self, thread_id: str, token_scope: str = TOKEN_SCOPE_ALL) -> None:
        self.thread_id = thread_id
        self.token_scope = token_scope
        self.usage = TokenUsage()
        self._seen_nodes: set = set()
        self._turn = 0
        self._buffered: List[str] = []
        self._tool_calls: Dict[str, Dict[str, Any]] = {}

    # -- custom channel ------------------------------------------------

    def map_custom(self, payload: Any) -> List[StreamEvent]:
        """Map one ``stream_mode="custom"`` payload."""
        if not isinstance(payload, dict):
            return []
        kind = payload.get("kind")
        if kind == CUSTOM_TOKEN:
            text = payload.get("text") or ""
            if not text:
                return []
            self._turn += 1
            if self.token_scope == TOKEN_SCOPE_FINAL and self._tool_calls:
                # A tool call already happened: this is the post-tool answer.
                return [StreamEvent("token", {"text": text, "turn": self._turn})]
            if self.token_scope == TOKEN_SCOPE_FINAL:
                self._buffered.append(text)
                self._turn -= 1
                return []
            return [StreamEvent("token", {"text": text, "turn": self._turn})]
        if kind == CUSTOM_TOOL_CALL:
            call = {
                "id": str(payload.get("id") or ""),
                "name": str(payload.get("name") or ""),
                "args": payload.get("args") or {},
            }
            if call["id"]:
                self._tool_calls[call["id"]] = call
            return [
                StreamEvent(
                    "tool_call",
                    {"id": call["id"], "name": call["name"], "args": call["args"]},
                )
            ]
        return []

    # -- messages channel ----------------------------------------------

    def map_messages(self, payload: Any) -> List[StreamEvent]:
        """Map one ``stream_mode="messages"`` chunk.

        In langgraph 1.x this channel yields ``(message, metadata)`` tuples,
        where ``metadata["langgraph_node"]`` names the producing node and
        ``metadata["langgraph_node"] == "__interrupt__"`` marks a paused run.
        The node name is the source for ``node_start``; interrupts are
        synthesized here because LangGraph exposes no dedicated event for them.
        """
        events: List[StreamEvent] = []
        if not isinstance(payload, (tuple, list)) or len(payload) != 2:
            return events
        message, metadata = payload
        node_name = ""
        if isinstance(metadata, dict):
            node_name = str(metadata.get("langgraph_node", "") or "")
        if not node_name:
            # Older/alternate shape: (node_name, message)
            if isinstance(message, str):
                node_name = message
            else:
                return events

        if node_name == "__interrupt__":
            interrupt_payload = _extract_interrupt_value(message)
            if interrupt_payload is not None:
                events.append(self._build_interrupt(interrupt_payload))
            return events

        if self._mark_node(node_name):
            events.append(StreamEvent("node_start", {"node": node_name}))
        return events

    def map_updates(self, payload: Any) -> List[StreamEvent]:
        """Map one ``stream_mode="updates"`` chunk.

        This channel yields node-keyed state deltas (``{"agent": {...}}``) plus,
        for a paused run, a top-level ``__interrupt__`` key. LangGraph exposes
        no dedicated interrupt event, so it is synthesized from that key.
        """
        events: List[StreamEvent] = []
        if not isinstance(payload, dict):
            return events

        if "__interrupt__" in payload:
            interrupt_payload = _extract_interrupt_value(payload["__interrupt__"])
            if interrupt_payload is not None:
                events.append(self._build_interrupt(interrupt_payload))
            return events

        for node_name, update in payload.items():
            if self._mark_node(str(node_name)):
                events.append(StreamEvent("node_start", {"node": str(node_name)}))
        return events

    def _mark_node(self, node: str) -> bool:
        """Record a node sighting; return True only on the first occurrence."""
        if node in self._seen_nodes:
            return False
        self._seen_nodes.add(node)
        return True

    def _build_interrupt(self, payload: Dict[str, Any]) -> StreamEvent:
        tools = payload.get("tools") or []
        resume_key = f"{self.thread_id}:{tools[0].get('id')}" if tools else self.thread_id
        return StreamEvent(
            "interrupt",
            {
                "thread_id": self.thread_id,
                "question": payload.get("question", "需要确认后才能继续。"),
                "resume_key": resume_key,
                "tools": tools,
            },
        )

    # -- finalization ---------------------------------------------------

    def flush_final_scope(self) -> List[StreamEvent]:
        """Emit buffered tokens (token_scope="final", no tool call happened)."""
        if not self._buffered:
            return []
        text = "".join(self._buffered)
        self._buffered = []
        self._turn += 1
        return [StreamEvent("token", {"text": text, "turn": self._turn})]

    def note_tool_result(self, call_id: str, name: str, content: str, status: str) -> None:
        """Record a completed tool call (used by the messages channel)."""
        if call_id:
            self._tool_calls.setdefault(
                call_id, {"id": call_id, "name": name, "args": {}}
            )


def _extract_interrupt_value(message: Any) -> Optional[Dict[str, Any]]:
    """Unwrap an Interrupt object (or list of them) into a plain dict."""
    if isinstance(message, (list, tuple)):
        if not message:
            return None
        message = message[0]
    value = getattr(message, "value", message)
    if isinstance(value, dict):
        return dict(value)
    return {"question": str(value)}
