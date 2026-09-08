"""
qa_service.retrieval — 向量检索模块。

调用链：
    query str
      → embedding_service.get_embedder().embed_query()   （bge-m3 编码）
      → vector_service.ChromaStore.query()               （Top-K 最近邻）
      → List[RetrievedChunk]                             （内部 DTO）

不修改 embedding_service / vector_service 的任何现有代码。
"""

from __future__ import annotations

import logging
from typing import List

from embedding_service.embedder import get_embedder
from vector_service.chroma_store import ChromaStore
from qa_service import config
from qa_service.models import RetrievedChunk

logger = logging.getLogger(__name__)

# 模块级单例，避免每次检索都重新加载模型（bge-m3 首次加载较慢）
_embedder = None
_store = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        logger.info("Loading embedding model: %s", config.EMBEDDING_MODEL)
        _embedder = get_embedder(config.EMBEDDING_MODEL)
    return _embedder


def _get_store() -> ChromaStore:
    global _store
    if _store is None:
        _store = ChromaStore(model=config.EMBEDDING_MODEL)
    return _store


def retrieve(query: str, k: int = config.TOP_K) -> List[RetrievedChunk]:
    """
    对 query 做向量编码，在 ChromaDB 中检索 Top-K 最近邻，
    返回转换后的 RetrievedChunk 列表（按距离升序）。

    Args:
        query: 用户问题原文。
        k:     最多返回的 chunk 数量。

    Returns:
        List[RetrievedChunk]，可能为空（collection 为空或 query 为空时）。
    """
    if not query or not query.strip():
        logger.warning("retrieve() called with empty query; returning []")
        return []

    embedder = _get_embedder()
    store = _get_store()

    query_vector: List[float] = embedder.embed_query(query.strip())
    raw_results = store.query(query_vector, top_k=k)

    chunks: List[RetrievedChunk] = []
    for r in raw_results:
        chunks.append(
            RetrievedChunk(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                title=r.title,
                heading=r.heading,
                source_path=r.source_path,
                text=r.text,
                distance=r.distance,
                rank=r.rank,
            )
        )

    logger.info(
        "Retrieved %d chunks for query (top distance=%.4f)",
        len(chunks),
        chunks[0].distance if chunks else float("nan"),
    )
    return chunks


def is_confident(chunks: List[RetrievedChunk], threshold: float = config.CONFIDENCE_THRESHOLD) -> bool:
    """
    判断检索结果是否达到置信度要求。

    规则：chunks 非空，且 Top-1 的 cosine distance < threshold。
    cosine distance = 1 - cosine similarity，范围 [0, 2]，越小越相似。

    ⚠ threshold 初始值 0.5，未经校准，待有评测数据后调整。

    Args:
        chunks:    retrieve() 返回的结果列表（已按距离升序排列）。
        threshold: cosine distance 阈值。

    Returns:
        True  — 检索置信度足够，可进入生成阶段。
        False — 检索为空或 Top-1 距离超阈值，直接返回"未找到"。
    """
    if not chunks:
        return False
    top_distance = chunks[0].distance
    confident = top_distance < threshold
    logger.info(
        "Confidence check: top_distance=%.4f, threshold=%.4f, confident=%s",
        top_distance,
        threshold,
        confident,
    )
    return confident
