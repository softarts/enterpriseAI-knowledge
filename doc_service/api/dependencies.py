"""
Dependency wiring for the API layer.

Provides singleton instances of the service and its dependencies.
Keeps the API routes clean of initialization logic.
"""

from typing import Optional

from doc_service.core.config import settings
from doc_service.repositories.okf_document_repository import OKFDocumentRepository
from doc_service.retrieval.embedding_retriever import EmbeddingRetriever
from doc_service.retrieval.keyword_retriever import KeywordRetriever
from doc_service.services.knowledge_service import KnowledgeService

_service_instance: Optional[KnowledgeService] = None
_embedding_service_instance: Optional[KnowledgeService] = None
_shared_repository: Optional[OKFDocumentRepository] = None


def _get_repository() -> OKFDocumentRepository:
    """Lazily create and cache a shared OKF repository instance."""
    global _shared_repository
    if _shared_repository is None:
        _shared_repository = OKFDocumentRepository()
    return _shared_repository


def get_knowledge_service() -> KnowledgeService:
    """
    Lazily create and cache the default (keyword-backed) KnowledgeService singleton.

    Wires together:
      OKFDocumentRepository -> KeywordRetriever -> KnowledgeService

    This backs the existing REST /search and the MCP `query_documents` tool.
    """
    global _service_instance
    if _service_instance is None:
        repository = _get_repository()
        retriever = KeywordRetriever(repository=repository)
        _service_instance = KnowledgeService(repository=repository, retriever=retriever)
    return _service_instance


def get_embedding_knowledge_service() -> KnowledgeService:
    """
    Lazily create and cache an embedding-backed KnowledgeService singleton.

    Wires together:
      OKFDocumentRepository -> EmbeddingRetriever -> KnowledgeService

    This backs the MCP `search_knowledge` tool. It shares the same repository
    (for document-level access) but swaps the retrieval backend to SBERT vector
    similarity. The retriever is chosen behind the same `Retriever` protocol, so
    a future ChromaRetriever can replace EmbeddingRetriever here without any
    change to the service or MCP tools.
    """
    global _embedding_service_instance
    if _embedding_service_instance is None:
        repository = _get_repository()
        retriever = EmbeddingRetriever()
        _embedding_service_instance = KnowledgeService(
            repository=repository, retriever=retriever
        )
    return _embedding_service_instance


from embedding_service.embedder import LocalEmbedder
from vector_service.chroma_store import ChromaStore

_chroma_store_instance: Optional[ChromaStore] = None
_local_embedder_instance: Optional[LocalEmbedder] = None


def get_chroma_store() -> ChromaStore:
    """
    Lazily create and cache a ChromaStore singleton (persistent Chroma at vector_db/).

    Used by the MCP `search_chroma` tool. The store only does vector queries —
    it does NOT embed text, keeping embedding and storage decoupled.
    """
    global _chroma_store_instance
    if _chroma_store_instance is None:
        _chroma_store_instance = ChromaStore()
    return _chroma_store_instance


def get_local_embedder() -> LocalEmbedder:
    """
    Lazily create and cache a LocalEmbedder singleton (SBERT all-MiniLM-L6-v2).

    Used by the MCP `search_chroma` tool to encode the query text into a vector
    before sending it to Chroma.
    """
    global _local_embedder_instance
    if _local_embedder_instance is None:
        _local_embedder_instance = LocalEmbedder()
    return _local_embedder_instance


def reset_service() -> None:
    """Reset the cached service instances. Used in tests."""
    global _service_instance, _embedding_service_instance, _shared_repository
    global _chroma_store_instance, _local_embedder_instance
    _service_instance = None
    _embedding_service_instance = None
    _shared_repository = None
    _chroma_store_instance = None
    _local_embedder_instance = None
