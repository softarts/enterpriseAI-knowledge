"""Per-turn call trace: aggregated LLM calls, tool calls, HTTP attempts, spans.

Four kinds of entries, deliberately kept separate so the UI can badge them
differently:

- ``kind="llm"``  — **one entry per LLM call**, carrying that call's request
  and its *aggregated* response. Produced by ``LlmTraceHandler`` from
  LangChain's ``on_chat_model_start`` / ``on_llm_end`` callbacks, so it is
  emitted exactly once per call regardless of how the provider streamed the
  answer on the wire.
- ``kind="tool"`` — one entry per executed tool call, from ``on_tool_start`` /
  ``on_tool_end``. This is the only layer that can see tools whose HTTP
  transport is *not* httpx: ``web_search`` reaches Tavily through
  ``requests`` / ``aiohttp``, so the httpx hooks below never fire for it.
- ``kind="http"`` — one entry per actual HTTP attempt to the LLM API
  (request + response are two separate entries, correlated by
  ``attempt_seq``); a retried request produces its own pair with the next
  ``attempt_seq``, so retries are visible without any separate retry-tracking
  logic.
- ``kind="local"`` — one entry per local function/graph-node span (agent
  node, hitl_gate, route_after_hitl's budget decision, force_finalize).

Why the callback layer exists: the graph nodes used to hand-aggregate streamed
chunks and call ``record_local(...)`` themselves, which meant re-implementing
the merge that langchain-core already performs before the node sees the
result. ``on_llm_end`` is handed that already-merged message directly, so the
recorded payload is the real one (tool calls included) and each LLM call maps
to exactly one trace entry.

``kind="http"`` stays as the transport-level layer underneath — "how many
attempts, which status code, what did we actually put on the wire". It answers
a different question from the ``llm`` entry ("what did the model say"), which is
why both exist for every call: ``on_chat_model_start`` publishes the innermost
in-flight run_id into a ContextVar, the httpx request hook stamps it onto the
request's extensions, and the response hook reads it back, so every
``llm_request``/``llm_response`` pair carries the same ``llm_call_id`` as the
``llm`` row it belongs under. The request body in particular is only visible at
this layer — it is captured off httpx's replayable ``ByteStream``, so it
includes the ``stream`` / ``stream_options`` flags and exact tool schema that
langchain-openai adds internally, which the ``llm`` row's LangChain-side
request summary cannot show. The response body is deliberately never read (it
is an SSE stream LangChain is consuming); the aggregated answer lives on the
``llm`` row.

Entries are collected per-turn via a ``contextvars.ContextVar`` so concurrent
requests (and the sync/async boundary LangChain crosses internally) don't mix
each other's traces. Nothing here may ever raise into the real request path —
this is diagnostics only, same philosophy as
``graph.py``'s ``_build_request_payload_preview``.
"""

from __future__ import annotations

import itertools
import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, List, Optional

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


def _short_conversation(entry: Dict[str, Any]) -> str:
    """A short, greppable conversation tag for the log line prefix.

    The full id also appears inside the JSON payload, but a fixed-width prefix
    means ``grep conversation-ae17`` works directly on the log text without
    parsing JSON, and consecutive turns of one conversation group together
    visually.
    """
    conversation_id = entry.get("conversation_id")
    if not conversation_id:
        return "-"
    text = str(conversation_id)
    # Conversation ids look like "conversation-<uuid>"; keep the readable head.
    head, _, tail = text.rpartition("-")
    return f"{head}-{tail[:8]}" if head else text[:16]


def _log_entry(entry: Dict[str, Any]) -> None:
    """Mirror every captured entry into the regular log stream (console +
    chat_service/run.py's log file), so a failed turn can be analyzed
    straight from the log instead of only from the in-memory trace sink
    (which the UI only ever sees for the request that's still in flight).
    """
    try:
        logger.info(
            "call_trace.entry [%s] %s",
            _short_conversation(entry),
            json.dumps(entry, ensure_ascii=False, default=str),
        )
    except Exception:  # noqa: BLE001 - tracing must never break a real request
        pass

_SINK: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar("call_trace_sink", default=None)
_attempt_seq = itertools.count(1)

_REDACT_HEADERS = {"authorization", "api-key", "x-api-key"}

# The httpx hooks and the LangChain callbacks fire on the same context but
# through different frameworks, so "which LLM call is this HTTP attempt part
# of" is answered with a ContextVar holding the innermost in-flight call's
# id. Set by the handler below at on_chat_model_start, cleared at on_llm_end.
_CURRENT_LLM_CALL: ContextVar[Optional[str]] = ContextVar(
    "call_trace_current_llm_call", default=None
)

# Conversation (thread) id for the turn being traced, so every trace row and
# every log line says which conversation it belongs to. Set by trace_scope().
_CURRENT_CONVERSATION: ContextVar[Optional[str]] = ContextVar(
    "call_trace_conversation_id", default=None
)

# Bound on error strings only. Request/response/tool payloads are NOT clipped:
# the trace is a debugging tool, and a silently shortened body is worse than a
# long one (you cannot tell a truncated payload from a genuinely small one).
# Error text is capped because an exception's str() can be arbitrarily large
# and carries no debugging value past a few hundred characters.
MAX_ERROR_CHARS = 500


def _error_text(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARS]


@contextmanager
def trace_scope(conversation_id: Optional[str] = None) -> Iterator[List[Dict[str, Any]]]:
    """Open a fresh per-turn trace sink; yields the list entries land in.

    ``conversation_id`` is stamped onto every entry recorded in this scope
    (see ``_append_timed``) so a trace row or log line is attributable to a
    conversation without having to correlate by timestamp.

    Safe to nest/reuse across the sync (`invoke`) and async (`astream`)
    graph entry points — each call gets its own list and context token.

    The ``reset`` is guarded because a ContextVar token may only be reset in
    the Context that created it. That guarantee does not hold when the caller
    is a *generator* suspended across a ``yield``: Starlette drives the SSE
    body iterator, and if the client disconnects (or a frame fails to
    serialize) the generator is finalized from a different task, running this
    ``finally`` in a different Context. ``reset`` would then raise
    ``ValueError: ... was created in a different Context``, which surfaces as
    "Exception in ASGI application" and masks the error that actually caused
    the teardown. Losing the token reset is harmless — the Context that set it
    is being discarded anyway — so degrade quietly instead.
    """
    entries: List[Dict[str, Any]] = []
    token = _SINK.set(entries)
    conversation_token = _CURRENT_CONVERSATION.set(conversation_id)
    try:
        yield entries
    finally:
        try:
            _CURRENT_CONVERSATION.reset(conversation_token)
        except ValueError:
            logger.debug("call_trace.trace_scope.cross_context_reset", exc_info=True)
        try:
            _SINK.reset(token)
        except ValueError:
            logger.debug("call_trace.trace_scope.cross_context_reset", exc_info=True)


def _append(entry: Dict[str, Any]) -> None:
    """Log an entry and hand it to the active per-turn sink, if any."""
    _log_entry(entry)
    sink = _SINK.get()
    if sink is not None:
        sink.append(entry)


def _append_timed(
    kind: str,
    name: str,
    detail: Dict[str, Any],
    status: str = "ok",
    duration_ms: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build one entry, log it, push it to the sink, and return it.

    Returning the entry lets callers keep a reference to the *same* dict they
    handed to the sink, so a later "finalize this entry in place" update is
    visible to a consumer that is already draining the list by reference.
    """
    entry: Dict[str, Any] = {
        "kind": kind,
        "name": name,
        "status": status,
        "detail": detail,
        "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        # Which conversation this row belongs to, stamped on every entry so a
        # log line or trace row is self-identifying — several conversations
        # interleave in one log file and one UI timeline.
        "conversation_id": _CURRENT_CONVERSATION.get(),
    }
    if extra:
        entry.update(extra)
    _append(entry)
    return entry


def record_local(
    name: str,
    detail: Dict[str, Any],
    status: str = "ok",
    duration_ms: Optional[float] = None,
) -> None:
    """Record one local function/node span for the current turn, if any."""
    try:
        _append_timed("local", name, detail, status, duration_ms)
    except Exception:  # noqa: BLE001 - tracing must never break a real request
        logger.debug("call_trace.record_local.failed", exc_info=True)


def record_tool(
    name: str,
    detail: Dict[str, Any],
    status: str = "ok",
    duration_ms: Optional[float] = None,
    tool_call_id: Optional[str] = None,
) -> None:
    """Record one executed tool call for the current turn, if any."""
    try:
        extra = {"tool_call_id": tool_call_id} if tool_call_id else None
        _append_timed("tool", name, detail, status, duration_ms, extra)
    except Exception:  # noqa: BLE001 - tracing must never break a real request
        logger.debug("call_trace.record_tool.failed", exc_info=True)


def _redact_headers(headers: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        items = headers.items() if hasattr(headers, "items") else list(headers)
        for key, value in items:
            out[str(key)] = "***" if str(key).lower() in _REDACT_HEADERS else str(value)
    except Exception:  # noqa: BLE001
        pass
    return out


def _on_request(request: Any) -> None:
    try:
        attempt = next(_attempt_seq)
        request.extensions["call_trace_attempt"] = attempt
        request.extensions["call_trace_started"] = time.perf_counter()
        # Record the outbound body. The OpenAI SDK builds it as a small,
        # replayable JSON document (httpx keeps it as a ByteStream, so reading
        # `request.content` here consumes nothing LangChain needs), which makes
        # this the only place the *actual* wire payload is visible — including
        # the `stream` / `stream_options` flags langchain-openai adds
        # internally, which a locally rebuilt preview therefore misses.
        body: Optional[str] = None
        try:
            raw_body = getattr(request, "content", None)
            if raw_body:
                body = raw_body.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - body capture is best-effort
            body = None
        # Correlate this HTTP attempt with the LLM call that issued it, so the
        # transport layer can be read underneath the `llm` entry.
        llm_call_id = _CURRENT_LLM_CALL.get()
        if llm_call_id is not None:
            request.extensions["call_trace_llm_call_id"] = llm_call_id
        _append_timed(
            "http",
            "llm_request",
            {
                "method": request.method,
                "url": str(request.url),
                "attempt": attempt,
                "headers": _redact_headers(request.headers),
                "body": body,
            },
            status="pending",
            extra={"llm_call_id": llm_call_id} if llm_call_id else None,
        )
    except Exception:  # noqa: BLE001 - tracing must never break a real request
        logger.debug("call_trace.on_request.failed", exc_info=True)


def _on_response(response: Any) -> None:
    try:
        request = response.request
        attempt = request.extensions.get("call_trace_attempt")
        started = request.extensions.get("call_trace_started")
        duration_ms = (time.perf_counter() - started) * 1000 if started is not None else None
        # Response body is intentionally never read here: chat-completion
        # calls stream as SSE, and consuming the body in this hook would steal
        # it from LangChain's own stream consumer. The aggregated answer is
        # recorded instead by the `kind="llm"` entry's response.
        llm_call_id = request.extensions.get("call_trace_llm_call_id")
        _append_timed(
            "http",
            "llm_response",
            {
                "method": request.method,
                "url": str(request.url),
                "attempt": attempt,
                "status_code": response.status_code,
            },
            status="ok" if response.status_code < 400 else "error",
            duration_ms=duration_ms,
            extra={"llm_call_id": llm_call_id} if llm_call_id else None,
        )
    except Exception:  # noqa: BLE001 - tracing must never break a real request
        logger.debug("call_trace.on_response.failed", exc_info=True)


async def _on_request_async(request: Any) -> None:
    _on_request(request)


async def _on_response_async(response: Any) -> None:
    _on_response(response)


def build_traced_http_clients():
    """Build one (sync httpx.Client, async httpx.AsyncClient) pair whose
    request/response event hooks append to whichever trace_scope() is
    currently active on this context — or do nothing if none is.

    httpx requires *sync* hook callables on ``Client`` and *coroutine*
    hook callables on ``AsyncClient`` (``await hook(request)`` is called
    unconditionally) — passing the same sync hooks to both raises
    ``TypeError: 'NoneType' object can't be awaited`` deep inside
    ``_send_handling_redirects`` the moment an async call is made, so the
    two clients deliberately get distinct hook callables here.

    Lazily imports httpx so modules that never touch tracing don't pay for
    the import. Returns (None, None) if httpx isn't installed (shouldn't
    happen: it's a transitive dependency of openai/langchain_openai).
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx ships with openai
        logger.warning("call_trace.httpx_unavailable")
        return None, None

    sync_hooks = {"request": [_on_request], "response": [_on_response]}
    async_hooks = {"request": [_on_request_async], "response": [_on_response_async]}
    return (
        httpx.Client(event_hooks=sync_hooks),
        httpx.AsyncClient(event_hooks=async_hooks),
    )


# ---------------------------------------------------------------------------
# Callback handler: one trace entry per LLM call, one per tool call
# ---------------------------------------------------------------------------


def _summarize_tools(tools: Any) -> Optional[List[Dict[str, Any]]]:
    """Tool names + trimmed descriptions bound for this call.

    The full serialized schema is large and identical on every call of a turn;
    the trace only needs to show *which* tools the model was offered.
    """
    if not isinstance(tools, list):
        return None
    summary: List[Dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if not isinstance(function, dict):
            function = tool
        name = function.get("name")
        if not name:
            continue
        summary.append(
            {
                "name": name,
                "description": (function.get("description") or "")[:200] or None,
            }
        )
    return summary or None


# Streaming yields AIMessageChunk objects; report the plain role name so the
# trace reads the same for streamed and non-streamed calls.
_ROLE_BY_TYPE = {
    "human": "user",
    "AIMessageChunk": "assistant",
    "ai": "assistant",
    "AIMessage": "assistant",
    "system": "system",
    "tool": "tool",
    "ToolMessage": "tool",
}


def _message_to_dict(message: Any) -> Dict[str, Any]:
    """Render one LangChain message as a plain JSON-friendly dict."""
    message_type = getattr(message, "type", None) or getattr(message, "role", None)
    role = _ROLE_BY_TYPE.get(str(message_type), str(message_type or "unknown"))
    content = getattr(message, "content", None)
    if not isinstance(content, str):
        # v1-style content is a list of typed blocks; flatten to plain text so
        # the trace stays readable.
        if isinstance(content, list):
            parts: List[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    parts.append(str(block.get("text") or ""))
            content = "".join(parts)
        else:
            content = "" if content is None else str(content)
    entry: Dict[str, Any] = {"role": role, "content": content}
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        entry["tool_calls"] = [
            {
                "id": call.get("id"),
                "name": call.get("name"),
                "args": call.get("args"),
            }
            for call in tool_calls
            if isinstance(call, dict)
        ]
    for attribute in ("name", "tool_call_id"):
        value = getattr(message, attribute, None)
        if value:
            entry[attribute] = value
    return entry


def _summarize_llm_result(response: Any) -> Optional[Dict[str, Any]]:
    """Extract the aggregated message (plus usage) from an ``LLMResult``."""
    try:
        generations = getattr(response, "generations", None) or []
        if not generations or not generations[0]:
            return None
        message = generations[0][0].message
    except Exception:  # noqa: BLE001 - diagnostics must not break the call
        return None
    if message is None:
        return None
    summary = _message_to_dict(message)
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict):
        summary["usage"] = usage
    # finish_reason / model live in response_metadata for ChatOpenAI chunks;
    # carry the useful scalars only, not the whole metadata blob.
    metadata = getattr(message, "response_metadata", None) or {}
    scalars = {
        key: metadata[key]
        for key in ("model_name", "finish_reason", "system_fingerprint")
        if metadata.get(key) is not None
    }
    if scalars:
        summary["response_metadata"] = scalars
    return summary


class LlmTraceHandler(BaseCallbackHandler):
    """Records one ``kind="llm"`` entry per LLM call and one per tool call.

    Each LLM call produces exactly one sink append: a provisional entry at
    ``on_chat_model_start`` carrying the request, which is then updated **in
    place** at ``on_llm_end`` with the aggregated response. The in-place
    update matters for the streaming UI: ``chat_stream.py`` drains the sink
    incrementally as the run progresses, so an entry appended only at the end
    would land after every ``tool_call``/``tool_result`` event instead of in
    its real position.

    Subclassing ``BaseCallbackHandler`` (rather than writing a bare object)
    is what makes LangChain accept it — the callback manager reads
    ``run_inline`` and friends off the instance. A *sync* handler is invoked
    on the async path too (LangChain wraps it), so this single class covers
    both ``invoke`` and ``astream`` without a separate async twin.
    """

    def __init__(self) -> None:
        # LLM run_id -> {"entry": <dict appended to the sink>, "started": perf_counter}
        self._llm_calls: Dict[str, Dict[str, Any]] = {}
        # Tool run_id -> {"entry": <dict>, "started": perf_counter, "name": str}
        self._tool_calls: Dict[str, Dict[str, Any]] = {}

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _flatten_messages(messages: Any) -> List[Dict[str, Any]]:
        """LangChain passes a list-of-batches; flatten to one message list."""
        flat: List[Dict[str, Any]] = []
        if not isinstance(messages, list):
            return flat
        for batch in messages:
            if isinstance(batch, list):
                flat.extend(message for message in batch)
            elif batch is not None:
                flat.append(batch)
        return [_message_to_dict(message) for message in flat]

    def _begin_llm_call(self, run_id: str, messages: Any, kwargs: Any) -> None:
        """Append the provisional request entry for one LLM call."""
        params = (kwargs or {}).get("invocation_params") or {}
        request: Dict[str, Any] = {
            "messages": self._flatten_messages(messages),
            "model": params.get("model_name") or params.get("model"),
        }
        bound_tools = _summarize_tools(params.get("tools"))
        if bound_tools:
            request["tools_bound"] = bound_tools
        if params.get("stream") is not None:
            # Present because the model is configured streaming=True, so even
            # the "non-streaming" endpoints go out as SSE on the wire.
            request["stream"] = params["stream"]
        # Which graph node issued the call — this is what the removed
        # `record_local("agent", ...)` span used to convey, so an LLM call
        # stays attributable to `agent` vs `force_finalize` vs
        # `update_memory`'s structured extraction.
        metadata = (kwargs or {}).get("metadata") or {}
        node = metadata.get("langgraph_node")
        if node:
            request["node"] = node
        entry = _append_timed(
            "llm",
            "llm_call",
            {"request": request},
            status="pending",
            extra={"llm_call_id": run_id},
        )
        self._llm_calls[run_id] = {"entry": entry, "started": time.perf_counter()}
        _CURRENT_LLM_CALL.set(run_id)

    def _end_llm_call(
        self,
        run_id: Optional[str],
        response: Any,
        error: Optional[BaseException] = None,
    ) -> None:
        """Finalize the provisional entry with the aggregated response."""
        if not run_id:
            return
        state = self._llm_calls.pop(run_id, None)
        _CURRENT_LLM_CALL.set(None)
        if state is None:
            return
        entry: Dict[str, Any] = state["entry"]
        detail = entry.get("detail")
        if not isinstance(detail, dict):
            detail = {}
        summary = _summarize_llm_result(response) if response is not None else None
        if summary is not None:
            detail["response"] = summary
        if error is not None:
            detail["error"] = _error_text(error)
        entry["detail"] = detail
        entry["status"] = "error" if error is not None else "ok"
        entry["duration_ms"] = round(
            (time.perf_counter() - state["started"]) * 1000, 2
        )
        # Re-log the finalized row so the log file carries the aggregated
        # response too, not just the provisional request.
        _log_entry(entry)

    def _begin_tool_call(
        self,
        run_id: Optional[str],
        name: str,
        detail: Dict[str, Any],
        tool_call_id: Optional[str],
    ) -> None:
        entry = _append_timed(
            "tool",
            name,
            detail,
            status="running",
            extra={"tool_call_id": tool_call_id} if tool_call_id else None,
        )
        if run_id:
            self._tool_calls[run_id] = {
                "entry": entry,
                "started": time.perf_counter(),
                "name": name,
            }

    def _end_tool_call(
        self,
        run_id: Optional[str],
        output: Any,
        error: Optional[BaseException] = None,
    ) -> None:
        if not run_id:
            return
        state = self._tool_calls.pop(run_id, None)
        if state is None:
            return
        entry: Dict[str, Any] = state["entry"]
        detail = entry.get("detail")
        if not isinstance(detail, dict):
            detail = {}
        if error is not None:
            detail["error"] = _error_text(error)
        else:
            detail["result"] = _tool_result_text(output)
        entry["detail"] = detail
        entry["status"] = "error" if error is not None else "ok"
        entry["duration_ms"] = round(
            (time.perf_counter() - state["started"]) * 1000, 2
        )
        _log_entry(entry)

    # -- LLM callbacks (sync + async) ----------------------------------

    def on_chat_model_start(
        self,
        serialized: Any,
        messages: Any,
        *,
        run_id: Any = "",
        **kwargs: Any,
    ) -> None:
        try:
            # run_id arrives as a UUID *object*, not a str; it is echoed into
            # the trace (and from there into the SSE frame's `llm_call_id`),
            # so it has to be stringified here or json.dumps rejects it.
            self._begin_llm_call(str(run_id or ""), messages, kwargs)
        except Exception:  # noqa: BLE001 - tracing must never break a real request
            logger.debug("call_trace.on_chat_model_start.failed", exc_info=True)

    def on_llm_end(self, response: Any, *, run_id: Any = "", **kwargs: Any) -> None:
        try:
            self._end_llm_call(str(run_id or ""), response)
        except Exception:  # noqa: BLE001
            logger.debug("call_trace.on_llm_end.failed", exc_info=True)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: Any = "",
        **kwargs: Any,
    ) -> None:
        try:
            self._end_llm_call(str(run_id or ""), None, error=error)
        except Exception:  # noqa: BLE001
            logger.debug("call_trace.on_llm_error.failed", exc_info=True)

    # -- tool callbacks (sync + async) ---------------------------------

    def on_tool_start(
        self,
        serialized: Any,
        input_str: str,
        *,
        run_id: Any = "",
        inputs: Any = None,
        **kwargs: Any,
    ) -> None:
        try:
            name = (serialized or {}).get("name") or "tool"
            arguments = inputs if isinstance(inputs, dict) else {"input": input_str}
            self._begin_tool_call(
                str(run_id or ""),
                name,
                {"arguments": arguments},
                # tool_call_id is likewise a plain str, but normalize anyway so
                # a provider-supplied non-str id can't break serialization.
                tool_call_id=(
                    str(kwargs["tool_call_id"])
                    if kwargs.get("tool_call_id") is not None
                    else None
                ),
            )
        except Exception:  # noqa: BLE001
            logger.debug("call_trace.on_tool_start.failed", exc_info=True)

    def on_tool_end(self, output: Any, *, run_id: Any = "", **kwargs: Any) -> None:
        try:
            self._end_tool_call(str(run_id or ""), output)
        except Exception:  # noqa: BLE001
            logger.debug("call_trace.on_tool_end.failed", exc_info=True)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: Any = "",
        **kwargs: Any,
    ) -> None:
        try:
            self._end_tool_call(str(run_id or ""), None, error=error)
        except Exception:  # noqa: BLE001
            logger.debug("call_trace.on_tool_error.failed", exc_info=True)


def _tool_result_text(output: Any) -> str:
    """Best-effort plain text for a tool result (usually a ToolMessage)."""
    content = getattr(output, "content", None)
    if content is None:
        content = output
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(content)


def build_trace_callbacks() -> List[Any]:
    """Build the callback handler(s) to attach to a graph run's config.

    Returned as a list so callers can splat it into ``config["callbacks"]``
    without caring whether more than one handler is added later.
    """
    return [LlmTraceHandler()]
