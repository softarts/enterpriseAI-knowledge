"""
Embedding-based retriever implementation (SBERT vector similarity).

This is a second concrete backend behind the shared `Retriever` protocol,
alongside `KeywordRetriever`. It reuses the existing `embedding_service`
capability (LocalEmbedder + search_by_similarity + persisted embedding JSON)
rather than duplicating any embedding or similarity logic.

Backend today:  persisted SBERT embeddings under the `embedding/` directory.
Future backends: a `ChromaRetriever` (or other vector DB) can implement the
same `Retriever` protocol with zero changes to KnowledgeService / MCP tools.
"""

import logging
from pathlib import Path
from typing import List, Optional

from embedding_service.config import DEFAULT_EMBEDDING_DIR
from embedding_service.embedder import LocalEmbedder
from embedding_service.models import EmbeddedChunk
from embedding_service.search import SimilarityResult, search_by_similarity
from embedding_service.storage import load_all_embeddings

from doc_service.retrieval.retriever import ChunkResult

logger = logging.getLogger(__name__)


class EmbeddingRetriever:
    """
    Vector-similarity retriever satisfying the `Retriever` protocol.

    Loads persisted SBERT embeddings once (lazily), embeds the query with the
    same local model, and returns the top-K chunks by cosine similarity mapped
    into the shared `ChunkResult` type.
    """

    def __init__(self, embedding_dir: Optional[Path] = None) -> None:
        self._embedding_dir = Path(embedding_dir or DEFAULT_EMBEDDING_DIR)
        self._embedder: Optional[LocalEmbedder] = None
        self._chunks: Optional[List[EmbeddedChunk]] = None

    def retrieve(self, query: str, top_k: int = 5) -> List[ChunkResult]:
        """Retrieve top-K chunks by embedding cosine similarity."""
        if not query.strip():
            return []

        chunks = self._get_all_chunks()
        if not chunks:
            logger.warning(
                "EmbeddingRetriever has no embeddings loaded from %s. "
                "Run 'python embedding_service/main_import.py' to generate them.",
                self._embedding_dir,
            )
            return []

        query_vector = self._get_embedder().embed_query(query)
        results: List[SimilarityResult] = search_by_similarity(
            query_vector, chunks, top_k=top_k
        )
        return [
            ChunkResult(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                title=r.title,
                heading=r.heading,
                content=r.content,
                score=r.score,
                source_path=r.source_path,
            )
            for r in results
        ]

    def reload(self) -> None:
        """Invalidate the cached embeddings (e.g. after new imports)."""
        self._chunks = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_embedder(self) -> LocalEmbedder:
        if self._embedder is None:
            self._embedder = LocalEmbedder()
        return self._embedder

    def _get_all_chunks(self) -> List[EmbeddedChunk]:
        """Load all persisted embeddings (lazy, cached)."""
        if self._chunks is None:
            self._chunks = load_all_embeddings(self._embedding_dir)
        return self._chunks
