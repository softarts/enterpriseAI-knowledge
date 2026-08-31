"""
Knowledge Service — orchestration layer between API and data access.

Responsibilities:
  - list_documents (with filtering and pagination)
  - get_document (by ID)
  - search (delegated to Retriever)

This service does NOT:
  - Read files directly
  - Parse YAML
  - Handle HTTP request/response
  - Know about FastAPI
"""

from typing import List, Optional

from doc_service.domain.document import DocumentRecord
from doc_service.repositories.okf_document_repository import OKFDocumentRepository
from doc_service.retrieval.keyword_retriever import KeywordRetriever
from doc_service.retrieval.retriever import ChunkResult


class KnowledgeService:
    """
    Core service that orchestrates document access and retrieval.

    Depends on:
      - A document repository (currently OKFDocumentRepository)
      - A retriever (currently KeywordRetriever)

    Both can be swapped via constructor injection.
    """

    def __init__(
        self,
        repository: OKFDocumentRepository,
        retriever: KeywordRetriever,
    ) -> None:
        self._repository = repository
        self._retriever = retriever

    def list_documents(
        self,
        keyword: Optional[str] = None,
        tag: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[DocumentRecord], int]:
        """
        List documents with optional filtering and pagination.

        Args:
            keyword: Filter by title keyword.
            tag: Filter by tag.
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            Tuple of (paginated document list, total count before pagination).
        """
        all_docs = self._repository.list_documents(keyword=keyword, tag=tag)
        total = len(all_docs)

        # Apply pagination
        start = (page - 1) * page_size
        end = start + page_size
        paginated = all_docs[start:end]

        return paginated, total

    def get_document(self, document_id: str) -> Optional[DocumentRecord]:
        """
        Get a single document by ID.

        Returns None if not found.
        """
        return self._repository.get_document(document_id)

    def search(self, query: str, top_k: int = 5) -> List[ChunkResult]:
        """
        Search for relevant document chunks.

        Delegates to the configured Retriever implementation.

        Args:
            query: The search query.
            top_k: Max number of results.

        Returns:
            List of ChunkResult sorted by relevance.
        """
        return self._retriever.retrieve(query=query, top_k=top_k)

    def reload(self) -> None:
        """Reload all data from disk (useful after new imports)."""
        self._repository.reload()
        self._retriever.reload()
