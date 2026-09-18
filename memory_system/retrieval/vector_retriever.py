"""
memory_system.retrieval.vector_retriever — ChromaDB-backed Retriever.

ChromaRetriever implements the Retriever interface using ChromaVectorStore
for embedding similarity search and SQLiteStore for memory metadata lookup.

Source hydration (fetching the raw source turn) is done in service.py,
not here. This keeps retrieval focused on similarity search only.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from memory_system.embedding import Embedder
from memory_system.models import Memory, MemoryStatus, RetrievedMemory
from memory_system.retrieval.base import Retriever
from memory_system.storage.sqlite_store import SQLiteStore
from memory_system.storage.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class ChromaRetriever(Retriever):
    """
    Retrieves memories by embedding similarity via ChromaDB.

    Filters ensure only ACTIVE memories are returned — deprecated memories
    are silently excluded at the vector index level.
    """

    def __init__(
        self,
        embedder: Embedder,
        vector_store: ChromaVectorStore,
        sqlite_store: SQLiteStore,
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store
        self._sqlite_store = sqlite_store

    def retrieve(
        self,
        query: str,
        top_k: int,
        filters: Dict[str, str],
    ) -> List[RetrievedMemory]:
        """
        1. Embed the query.
        2. Query Chroma with metadata filters (status=active).
        3. Look up full Memory metadata from SQLite (source of truth).
        4. Return RetrievedMemory list (source_turn not yet hydrated).

        Note: filters MUST include {"status": "active"} to exclude deprecated memories.
        """
        logger.info(
            "Retrieving memories: query_preview='%s' top_k=%d filters=%s",
            query[:60],
            top_k,
            filters,
        )

        query_embedding = self._embedder.embed(query)
        raw_results = self._vector_store.query(
            query_embedding=query_embedding,
            top_k=top_k,
            where=filters if filters else None,
        )

        retrieved: List[RetrievedMemory] = []
        for doc_id, similarity, _meta in raw_results:
            # Authoritative memory metadata comes from SQLite, not Chroma
            memory = self._sqlite_store.get_memory_by_id(doc_id)
            if memory is None:
                logger.warning("Memory in Chroma but not in SQLite: id=%s", doc_id)
                continue
            # Double-check status in SQLite (source of truth)
            if memory.status != MemoryStatus.ACTIVE:
                logger.debug(
                    "Skipping non-active memory from Chroma: id=%s status=%s",
                    doc_id,
                    memory.status,
                )
                continue
            retrieved.append(RetrievedMemory(memory=memory, similarity=similarity))
            logger.debug(
                "Retrieved memory: id=%s similarity=%.4f content='%s'",
                doc_id,
                similarity,
                memory.content[:60],
            )

        logger.info("Retrieval complete: %d memories found", len(retrieved))
        return retrieved
