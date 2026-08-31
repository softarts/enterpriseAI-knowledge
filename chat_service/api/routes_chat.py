"""
Chat API routes.

Endpoints:
    GET  /api/health  - liveness + config summary (never exposes the token).
    POST /api/chat    - single-turn Ask; returns answer + extensible trace.
"""

from fastapi import APIRouter

from chat_service.config import settings
from chat_service.models import ChatRequest, ChatResponse
from chat_service.services.chat_service import ChatService

router = APIRouter()

# One shared service instance (stateless; safe to reuse).
_chat_service = ChatService()


@router.get("/api/health")
def health() -> dict:
    """Report service status and whether an HF token is configured."""
    return {
        "service": settings.service_name,
        "version": settings.version,
        "model": settings.model,
        # Booleans only — never return the token value itself.
        "hf_token_configured": bool(settings.hf_token()),
    }


@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """
    Run the Ask flow: question -> HF LLM -> answer + trace.

    Errors (missing token, upstream failure, empty question) are returned as a
    200 response with `error` set and an error-annotated trace, so the UI can
    render them in the chat area and the Verbose panel.
    """
    result = _chat_service.ask(request.question)
    return ChatResponse(answer=result.answer, trace=result.trace, error=result.error)
