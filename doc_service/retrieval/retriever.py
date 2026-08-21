"""Retriever protocol definition.

Current implementation: KeywordRetriever
Future implementations: VectorRetriever, FAISSRetriever, HybridRetriever
"""

from dataclasses import dataclass, field
from typing import List, Optional, Protocol


@dataclass
class ChunkResult:
    """A single retrieval result at the chunk level."""

    chunk_id: str
    document_id: str
    title: str
    heading: Optional[str] = None
    content: str = ""
    score: float = 0.0
    source_path: str = ""


class Retriever(Protocol):
    """
    Abstract retriever interface.

    All retriever implementations must satisfy this protocol.
    The service layer depends only on this protocol, not on
    any concrete retriever.
    """

    def retrieve(self, query: str, top_k: int = 5) -> List[ChunkResult]:
        """
        Retrieve the most relevant chunks for a query.

        Args:
            query: The search query string.
            top_k: Maximum number of results to return.

        Returns:
            List of ChunkResult sorted by relevance (descending score).
        """
        ...
