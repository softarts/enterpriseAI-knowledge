"""Pydantic models for document import and taxonomy APIs."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ClassificationView(BaseModel):
    """User-facing classification result (breadcrumb + levels)."""

    level_1: Optional[str] = None
    level_2: Optional[str] = None
    level_3: Optional[str] = None
    breadcrumb: str = ""
    level_scores: Optional[Dict[str, float]] = Field(
        default=None, description="L1/L2/L3 classifier scores"
    )


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
    document_body: Optional[str] = Field(
        None, description="Extracted document text content"
    )
    file_size: Optional[int] = Field(None, description="Original file size in bytes")
    source: Optional[str] = Field(None, description="Document source, e.g. 'upload'")
    content_hash: Optional[str] = None
    deduplicated: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentSummary(BaseModel):
    """Lightweight document entry for paginated listings (no body)."""

    id: str
    filename: str
    import_state: str
    status: str
    classification: Optional[ClassificationView] = None
    file_size: Optional[int] = None
    source: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Paginated document listing."""

    items: List[DocumentSummary] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class DocumentPreviewResponse(BaseModel):
    """Full document content for preview."""

    id: str
    filename: str
    file_size: Optional[int] = None
    source: Optional[str] = None
    classification: Optional[ClassificationView] = None
    document_body: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TaxonomyNode(BaseModel):
    """A taxonomy node for the read-only taxonomy tree."""

    key: str
    name: str
    children: List["TaxonomyNode"] = Field(default_factory=list)
    document_count: int = Field(
        0, description="Number of imported documents in this (leaf) category"
    )


class TaxonomyResponse(BaseModel):
    """Read-only taxonomy tree (for display; no editing in this phase)."""

    taxonomy_version: str
    nodes: List[TaxonomyNode] = Field(default_factory=list)


class ImportErrorResponse(BaseModel):
    """Stable error envelope for import endpoints."""

    code: str
    message: str


TaxonomyNode.model_rebuild()
