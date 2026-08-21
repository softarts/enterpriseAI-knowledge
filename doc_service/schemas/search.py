"""Search-related API schemas."""

from typing import List, Optional

from pydantic import BaseModel


class SearchResult(BaseModel):
    """A single search result (chunk-level)."""

    chunk_id: str
    document_id: str
    title: str
    heading: Optional[str] = None
    content: str
    score: float
    source_path: str


class SearchResponse(BaseModel):
    """Response for GET /search."""

    query: str
    results: List[SearchResult]
