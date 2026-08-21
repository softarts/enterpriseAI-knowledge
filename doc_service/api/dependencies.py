"""
Dependency wiring for the API layer.

Provides singleton instances of the service and its dependencies.
Keeps the API routes clean of initialization logic.
"""

from typing import Optional

from doc_service.core.config import settings
from doc_service.repositories.okf_document_repository import OKFDocumentRepository
from doc_service.retrieval.keyword_retriever import KeywordRetriever
from doc_service.services.knowledge_service import KnowledgeService

_service_instance: Optional[KnowledgeService] = None


def get_knowledge_service() -> KnowledgeService:
    """
    Lazily create and cache the KnowledgeService singleton.

    Wires together:
      OKFDocumentRepository -> KeywordRetriever -> KnowledgeService
    """
    global _service_instance
    if _service_instance is None:
        repository = OKFDocumentRepository()
        retriever = KeywordRetriever(repository=repository)
        _service_instance = KnowledgeService(repository=repository, retriever=retriever)
    return _service_instance


def reset_service() -> None:
    """Reset the cached service instance. Used in tests."""
    global _service_instance
    _service_instance = None
