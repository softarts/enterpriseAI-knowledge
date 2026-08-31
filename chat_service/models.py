"""
Pydantic request/response models for chat_service.

The `trace` field is an open-ended dict so that future pipeline stages
(retrieval, context assembly, reranker, agent steps) can extend it without
breaking the API contract. See chat_service/trace.py for the builder.
"""

from typing import Any, Dict, List, Optional

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


# ---------------------------------------------------------------------------
# Document Import (MVP: single file, synchronous)
# ---------------------------------------------------------------------------


class ClassificationView(BaseModel):
    """User-facing classification result (breadcrumb + levels)."""

    level_1: Optional[str] = None
    level_2: Optional[str] = None
    level_3: Optional[str] = None
    breadcrumb: str = ""


class ImportDocumentResponse(BaseModel):
    """Response for import / get / confirm of a single document."""

    id: str
    filename: str
    import_state: str = Field(..., description="pending | imported")
    status: str = Field(..., description="classified | unknown")
    classification: Optional[ClassificationView] = Field(
        None, description="null when status is 'unknown'"
    )
    taxonomy_version: Optional[str] = None
    storage_path: Optional[str] = Field(
        None, description="Relative storage path; set only after confirm."
    )
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TaxonomyNode(BaseModel):
    """A taxonomy node for the read-only taxonomy tree."""

    key: str
    name: str
    children: List["TaxonomyNode"] = Field(default_factory=list)


class TaxonomyResponse(BaseModel):
    """Read-only taxonomy tree (for display; no editing in this phase)."""

    taxonomy_version: str
    nodes: List[TaxonomyNode] = Field(default_factory=list)


class ImportErrorResponse(BaseModel):
    """Stable error envelope for import endpoints."""

    code: str
    message: str


TaxonomyNode.model_rebuild()
