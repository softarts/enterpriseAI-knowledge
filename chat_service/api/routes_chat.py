"""
Chat API routes.

Endpoints:
    GET  /api/health  - liveness + config summary (never exposes the token).
    POST /api/chat    - single-turn Ask; returns answer + extensible trace.
"""

from typing import Optional

from fastapi import APIRouter, Header

from chat_service.services.chat.config import settings
from chat_service.services.chat.models import ChatRequest, ChatResponse
from chat_service.services.chat.chat_service import ChatService
from langchain_agent.app.runtime import create_memory_runtime
from qa_service import config as qa_config

router = APIRouter()

# Process-scoped Checkpointer runtime; it exists before requests are served.
_memory_runtime = create_memory_runtime()
_chat_service = ChatService(memory_runtime=_memory_runtime)


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
