import math
from dataclasses import dataclass
from typing import List, Optional

from embedding_service.models import EmbeddedChunk


@dataclass
class SimilarityResult:
    """
    Search match result with similarity score.
    """
    chunk_id: str
    document_id: str
    title: str
    heading: Optional[str]
    content: str
    source_path: str
    score: float


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.
    If vectors are already normalized (L2 norm = 1.0), this equals dot product.
    Formula: (A · B) / (||A|| * ||B||)
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot_product = 0.0
    norm_a = 0.0
    norm_b = 0.0

    for a, b in zip(vec_a, vec_b):
        dot_product += a * b
        norm_a += a * a
        norm_b += b * b

    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0

    return dot_product / (math.sqrt(norm_a) * math.sqrt(norm_b))


def search_by_similarity(
    query_vector: List[float],
    embedded_chunks: List[EmbeddedChunk],
    top_k: int = 5,
) -> List[SimilarityResult]:
    """
    Calculate cosine similarity between query vector and all embedded chunks,
    returning top-K matches sorted descending by score.
    """
    if not query_vector or not embedded_chunks:
        return []

    scored_results: List[SimilarityResult] = []
    for chunk in embedded_chunks:
        score = cosine_similarity(query_vector, chunk.embedding)
        scored_results.append(
            SimilarityResult(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                title=chunk.title,
                heading=chunk.heading,
                content=chunk.content,
                source_path=chunk.source_path,
                score=round(score, 4),
            )
        )

    scored_results.sort(key=lambda x: x.score, reverse=True)
    return scored_results[:top_k]
