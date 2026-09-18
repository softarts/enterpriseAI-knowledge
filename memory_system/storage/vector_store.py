"""
memory_system.storage.vector_store — ChromaDB wrapper.

Business code MUST NOT import chromadb directly.
All Chroma interactions go through ChromaVectorStore.

Design:
    Chroma is the RETRIEVAL INDEX only.
    SQLite is the source of truth for metadata and raw content.

    Each entry in Chroma corresponds to a memory in SQLite (same id).
    Metadata stored in Chroma: {conversation_id, status, created_at}
    This minimal metadata enables filtering without cross-referencing SQLite
    on every query.

    When status changes in SQLite (e.g., deprecated), caller must also
    call update_metadata() here to keep the index consistent.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """
    Thin wrapper around a single ChromaDB collection.

    All methods work with plain Python types — no Chroma objects leak out.
    """

    def __init__(self, persist_dir: str, collection_name: str) -> None:
        """
        Initialise (or load) a persistent Chroma collection.

        Args:
            persist_dir:     Directory where Chroma persists data.
            collection_name: Name of the collection to use.
        """
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError(
                "chromadb is required. Install with: pip install chromadb>=1.5.0"
            ) from exc

        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaVectorStore ready: dir=%s collection=%s count=%d",
            persist_dir,
            collection_name,
            self._collection.count(),
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(
        self,
        doc_id: str,
        embedding: List[float],
        metadata: Dict[str, Any],
        document: str,
    ) -> None:
        """
        Insert or update an entry in the collection.

        Args:
            doc_id:    Must match SQLite memories.id.
            embedding: Vector for the memory content.
            metadata:  Flat dict with string values (Chroma requirement).
            document:  Human-readable text (memory content, for debugging).
        """
        self._collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            metadatas=[metadata],
            documents=[document],
        )
        logger.debug("Upserted to Chroma: id=%s", doc_id)

    def update_metadata(self, doc_id: str, metadata: Dict[str, Any]) -> None:
        """Update metadata for an existing entry (e.g., when deprecating)."""
        self._collection.update(
            ids=[doc_id],
            metadatas=[metadata],
        )
        logger.debug("Updated Chroma metadata: id=%s", doc_id)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query(
        self,
        query_embedding: List[float],
        top_k: int,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Retrieve the top-k most similar entries.

        Args:
            query_embedding: Query vector.
            top_k:           Number of results to return.
            where:           Chroma metadata filter (e.g., {"status": "active"}).

        Returns:
            List of (id, similarity_score, metadata) tuples.
            similarity_score is cosine similarity in [0, 1] (higher = more similar).
        """
        count = self._collection.count()
        if count == 0:
            logger.debug("Chroma collection is empty, skipping query.")
            return []

        effective_k = min(top_k, count)

        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": effective_k,
            "include": ["metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        ids = results["ids"][0]
        distances = results["distances"][0]  # cosine distance in [0, 2]
        metadatas = results["metadatas"][0]

        output: List[Tuple[str, float, Dict[str, Any]]] = []
        for doc_id, dist, meta in zip(ids, distances, metadatas):
            # Convert cosine distance → similarity: similarity = 1 - dist/2
            # Chroma with hnsw:space=cosine returns distances in [0, 2]
            similarity = 1.0 - dist / 2.0
            output.append((doc_id, similarity, meta))

        logger.debug("Chroma query returned %d results (top_k=%d)", len(output), top_k)
        return output

    def count(self) -> int:
        """Return total number of entries in the collection."""
        return self._collection.count()
