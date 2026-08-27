"""
Pydantic request/response models for chat_service.

The `trace` field is an open-ended dict so that future pipeline stages
(retrieval, context assembly, reranker, agent steps) can extend it without
breaking the API contract. See chat_service/trace.py for the builder.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """A single-turn chat request from the UI."""

    question: str = Field(..., description="The user's question / prompt.")


class ChatResponse(BaseModel):
    """The answer plus an extensible execution trace."""

    answer: str = Field("", description="The LLM answer text.")
    trace: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured, extensible execution trace for this request.",
    )
    error: Optional[str] = Field(
        None,
        description="Human-readable error message when the request failed.",
    )
