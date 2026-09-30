"""Request and response models for the Checkpointer-backed chat API."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

# Streaming token scope.
#   "all"   — every answer-node LLM chunk, including rounds that decide tool calls
#   "final" — only the last round (the actual answer), earlier rounds buffered
TOKEN_SCOPES = ("all", "final")


class ChatRequest(BaseModel):
    question: str = Field(..., description="The user's question / prompt.")


class ChatResponse(BaseModel):
    answer: str = Field("", description="The LLM answer text.")
    trace: Dict[str, Any] = Field(default_factory=dict, description="Execution trace.")
    error: Optional[str] = Field(None, description="Human-readable error message.")


class StreamChatRequest(BaseModel):
    question: str = Field(..., description="The user's question / prompt.")
    token_scope: str = Field(
        "all",
        description='Token scope: "all" or "final".',
    )


class ChatResumeRequest(BaseModel):
    resume: Optional[Any] = Field(
        True,
        description="Value passed to Command(resume=...); false rejects the pending tool call.",
    )
    token_scope: str = Field("all", description='Token scope: "all" or "final".')
