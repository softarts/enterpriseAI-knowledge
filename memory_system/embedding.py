"""
memory_system.embedding — Embedding provider abstraction.

Two implementations:
    SentenceTransformerEmbedder  — local sentence-transformers (all-MiniLM-L6-v2)
    MockEmbedder                 — deterministic random vectors for smoke tests

Usage:
    from memory_system.embedding import get_embedder
    embedder = get_embedder()
    vector = embedder.embed(text)

All embedders return unit-normalised float vectors.
"""

from __future__ import annotations

import hashlib
import logging
import struct
from abc import ABC, abstractmethod
from typing import List

logger = logging.getLogger(__name__)


class Embedder(ABC):
    """Abstract embedder returning a unit-normalised float vector."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Return a normalised embedding vector for the given text."""
        ...


class SentenceTransformerEmbedder(Embedder):
    """
    Local sentence-transformers embedder using all-MiniLM-L6-v2 (dim=384).

    Requires: pip install sentence-transformers
    The model is downloaded on first use (~80 MB).
    """

    _MODEL_NAME = "all-MiniLM-L6-v2"
    _DIM = 384

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required. "
                "Install with: pip install sentence-transformers"
            ) from exc
        logger.info("Loading SentenceTransformer model: %s", self._MODEL_NAME)
        self._model = SentenceTransformer(self._MODEL_NAME)
        logger.info("SentenceTransformer ready: dim=%d", self._DIM)

    @property
    def dimension(self) -> int:
        return self._DIM

    def embed(self, text: str) -> List[float]:
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()


class MockEmbedder(Embedder):
    """
    Deterministic mock embedder for smoke tests.

    Generates a seeded pseudo-random unit vector from the SHA-256 hash of
    the input text, so identical texts always get identical vectors.
    NOT suitable for real semantic retrieval.
    """

    _DIM = 384

    @property
    def dimension(self) -> int:
        return self._DIM

    def embed(self, text: str) -> List[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Extend digest to exactly _DIM * 4 bytes by cycling
        needed = self._DIM * 4
        extended = bytearray()
        while len(extended) < needed:
            extended.extend(digest)
        raw_bytes = bytes(extended[:needed])
        floats = list(struct.unpack("{:d}f".format(self._DIM), raw_bytes))
        # Replace NaN/Inf from float bit patterns with 0
        floats = [f if (f == f and abs(f) < 1e30) else 0.0 for f in floats]
        # Normalise to unit vector
        norm = sum(x * x for x in floats) ** 0.5
        if norm == 0:
            floats[0] = 1.0
            norm = 1.0
        return [x / norm for x in floats]


def get_embedder() -> Embedder:
    """
    Factory: returns SentenceTransformerEmbedder or MockEmbedder based on config.

    Set EMBEDDING_MODEL=mock for smoke tests without sentence-transformers.
    Set EMBEDDING_MODEL=minilm (default) for local production use.
    """
    from memory_system import config

    model = config.EMBEDDING_MODEL.lower()
    if model == "mock":
        logger.warning(
            "Using MockEmbedder — vectors are NOT semantically meaningful. "
            "Set EMBEDDING_MODEL=minilm for real retrieval."
        )
        return MockEmbedder()
    if model == "minilm":
        return SentenceTransformerEmbedder()
    raise ValueError(
        f"Unknown EMBEDDING_MODEL: {model!r}. Supported: 'minilm', 'mock'"
    )
