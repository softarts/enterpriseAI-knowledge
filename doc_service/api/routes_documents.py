"""Document and search endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from doc_service.api.dependencies import get_knowledge_service
from doc_service.schemas.common import ErrorDetail, ErrorResponse
from doc_service.schemas.document import (
    DocumentDetail,
    DocumentListResponse,
    DocumentSummary,
)
from doc_service.schemas.search import SearchResponse, SearchResult

router = APIRouter()


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(
    keyword: Optional[str] = Query(None, description="Filter by title keyword"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> DocumentListResponse:
    """List all OKF documents with optional filtering and pagination."""
    service = get_knowledge_service()
    docs, total = service.list_documents(
        keyword=keyword, tag=tag, page=page, page_size=page_size
    )

    items = [
        DocumentSummary(
            document_id=doc.document_id,
            title=doc.title,
            author=doc.author,
            created_at=doc.created_at,
            tags=doc.tags,
            source_path=doc.source_path,
        )
        for doc in docs
    ]

    return DocumentListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetail,
    responses={404: {"model": ErrorResponse}},
)
def get_document(document_id: str) -> DocumentDetail:
    """Get a single document by ID, including full Markdown content."""
    service = get_knowledge_service()
    doc = service.get_document(document_id)

    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code="DOCUMENT_NOT_FOUND",
                    message=f"Document '{document_id}' was not found",
                )
            ).model_dump(),
        )

    return DocumentDetail(
        document_id=doc.document_id,
        title=doc.title,
        author=doc.author,
        created_at=doc.created_at,
        tags=doc.tags,
        source_path=doc.source_path,
        content=doc.content,
    )


@router.get("/search", response_model=SearchResponse)
def search_documents(
    q: str = Query(..., min_length=1, description="Search query"),
    top_k: int = Query(5, ge=1, le=50, description="Max results to return"),
) -> SearchResponse:
    """Search for relevant document chunks by keyword."""
    service = get_knowledge_service()
    chunk_results = service.search(query=q, top_k=top_k)

    results = [
        SearchResult(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            title=r.title,
            heading=r.heading,
            content=r.content,
            score=r.score,
            source_path=r.source_path,
        )
        for r in chunk_results
    ]

    return SearchResponse(query=q, results=results)
