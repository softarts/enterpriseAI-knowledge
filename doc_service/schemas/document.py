"""Document-related API schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class DocumentSummary(BaseModel):
    """Summary representation of a document (used in list responses)."""

    document_id: str
    title: str
    author: str
    created_at: Optional[str] = None
    tags: List[str] = []
    source_path: str


class DocumentDetail(BaseModel):
    """Full document representation including content."""

    document_id: str
    title: str
    author: str
    created_at: Optional[str] = None
    tags: List[str] = []
    source_path: str
    content: str


class DocumentListResponse(BaseModel):
    """Paginated list of document summaries."""

    items: List[DocumentSummary]
    total: int
    page: int
    page_size: int
