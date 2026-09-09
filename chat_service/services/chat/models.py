"""Request and response models for the legacy direct-chat API."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., description="The user's question / prompt.")


class ChatResponse(BaseModel):
    answer: str = Field("", description="The LLM answer text.")
    trace: Dict[str, Any] = Field(default_factory=dict, description="Execution trace.")
    error: Optional[str] = Field(None, description="Human-readable error message.")
