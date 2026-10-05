"""
Chat API routes.

Endpoints:
    GET  /api/health       - liveness + config summary (never exposes the token).
    POST /api/chat         - single-turn Ask; returns answer + extensible trace.
    POST /api/chat/stream  - SSE stream of one turn (token/tool_call/tool_result/...).
    POST /api/chat/resume  - resume an interrupted (HITL) turn.
    POST /api/chat/cancel  - cancel an in-flight stream by conversation id.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from chat_service.services.chat.config import settings
from chat_service.services.chat.models import (
    ChatRequest,
    ChatResponse,
    ChatResumeRequest,
    StreamChatRequest,
)
from chat_service.services.chat.chat_service import ChatService
from chat_service.services.chat.chat_stream import ChatStreamService
from langchain_agent.app.runtime import create_memory_runtime
from qa_service import config as qa_config

logger = logging.getLogger(__name__)

router = APIRouter()

# Process-scoped Checkpointer runtime; it exists before requests are served.
_memory_runtime = create_memory_runtime()
_chat_service = ChatService(memory_runtime=_memory_runtime)
_chat_stream_service = ChatStreamService(memory_runtime=_memory_runtime)

# In-flight streaming tasks keyed by conversation id, so an explicit cancel
# request can abort server-side execution (not just the client connection).
_ACTIVE_STREAMS: Dict[str, asyncio.Task] = {}


@router.get("/api/health")
def health() -> dict:
    """Report service status and whether the shared LLM config is complete."""
    return {
        "service": settings.service_name,
        "version": settings.version,
        "model": qa_config.LLM_MODEL,
        "llm_configured": bool(
            qa_config.LLM_API_KEY and qa_config.LLM_BASE_URL and qa_config.LLM_MODEL
        ),
    }


@router.post("/api/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    conversation_id: str = Header(alias="X-Conversation-Id"),
    user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> ChatResponse:
    """
    Run pure chat with Checkpointer history scoped to X-Conversation-Id.

    X-User-Id scopes the long-term memory namespace; when absent the runtime
    falls back to a default user for this personal deployment.

    Errors (missing token, upstream failure, empty question) are returned as a
    200 response with `error` set and an error-annotated trace, so the UI can
    render them in the chat area and the Verbose panel.
    """
    result = _chat_service.ask(
        request.question,
        thread_id=conversation_id,
        user_id=user_id,
    )
    return ChatResponse(answer=result.answer, trace=result.trace, error=result.error)


# ---------------------------------------------------------------------------
# Streaming endpoints
# ---------------------------------------------------------------------------


def _sse_response(event_iterator) -> StreamingResponse:
    """Wrap a protocol-event iterator in an SSE response."""
    return StreamingResponse(
        event_iterator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Disable proxy buffering so tokens reach the browser immediately.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/chat/stream")
async def chat_stream(
    request: StreamChatRequest,
    raw_request: Request,
    conversation_id: str = Header(alias="X-Conversation-Id"),
    user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id"),
) -> StreamingResponse:
    """
    Stream one chat turn as Server-Sent Events.

    Event types: token, tool_call, tool_result, node_start, interrupt, done, error.
    Each SSE frame is one JSON object: ``data: {"type": ..., ...}``.

    The stream always terminates with a ``done`` event, so the client can
    unconditionally clear its loading state. If the client disconnects, the
    underlying graph execution is cancelled.
    """
    token_scope = request.token_scope
    active_trace_id = request.trace_id or trace_id

    async def event_stream():
        task = asyncio.current_task()
        if task is not None:
            _ACTIVE_STREAMS[conversation_id] = task
        try:
            async for event in _chat_stream_service.stream_turn(
                question=request.question,
                thread_id=conversation_id,
                user_id=user_id,
                token_scope=token_scope,
                trace_id=active_trace_id,
            ):
                # Propagate client disconnects as cancellation of the graph run.
                if await raw_request.is_disconnected():
                    logger.info("chat.stream.client_disconnected id=%s", conversation_id)
                    break
                yield event.to_sse()
        except asyncio.CancelledError:
            logger.info("chat.stream.cancelled id=%s", conversation_id)
            raise
        finally:
            _ACTIVE_STREAMS.pop(conversation_id, None)

    return _sse_response(event_stream())


@router.post("/api/chat/resume")
async def chat_resume(
    request: ChatResumeRequest,
    conversation_id: str = Header(alias="X-Conversation-Id"),
    user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id"),
) -> StreamingResponse:
    """
    Resume a turn paused by the HITL gate (before an internet-touching tool).

    Continues from the exact interrupt point in the same Checkpointer, so the
    LLM call that requested the tool is not repeated.
    """
    resume_value = request.resume if request.resume is not None else True
    active_trace_id = request.trace_id or trace_id

    async def event_stream():
        async for event in _chat_stream_service.stream_resume(
            thread_id=conversation_id,
            user_id=user_id,
            resume_value=resume_value,
            token_scope=request.token_scope,
            trace_id=active_trace_id,
        ):
            yield event.to_sse()

    return _sse_response(event_stream())


@router.post("/api/chat/cancel")
async def chat_cancel(
    conversation_id: str = Header(alias="X-Conversation-Id"),
) -> Dict[str, Any]:
    """
    Cancel an in-flight stream for this conversation.

    The client aborts its fetch; this endpoint additionally cancels the
    server-side graph task so the LLM call stops immediately.
    """
    task = _ACTIVE_STREAMS.pop(conversation_id, None)
    if task is None or task.done():
        return {"cancelled": False, "reason": "no active stream"}
    task.cancel()
    logger.info("chat.stream.cancel_requested id=%s", conversation_id)
    return {"cancelled": True}
