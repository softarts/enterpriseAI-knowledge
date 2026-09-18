"""
memory_system.retrieval.base — Abstract Retriever interface.

Business code depends on this interface, not on ChromaRetriever directly.
This enables future swapping to HybridRetriever, RerankerRetriever, etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

from memory_system.models import RetrievedMemory


class Retriever(ABC):
    """
    Abstract semantic retriever.

    Implementations embed the query and search the vector index,
    returning Memory objects hydrated from SQLite.
    """

    @abstractmethod
    def retrieve(
        self,
        query: str,
        top_k: int,
        filters: Dict[str, str],
    ) -> List[RetrievedMemory]:
        """
        Retrieve semantically relevant memories.

        Args:
            query:   Natural language query (already rewritten).
            top_k:   Maximum number of results.
            filters: Metadata filters (e.g., {"status": "active"}).

        Returns:
            List of RetrievedMemory objects with similarity scores.
            Source turns are NOT hydrated here — call source_hydrate() separately.
        """
        ...
