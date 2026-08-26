"""
Thin wrapper around a Chroma persistent collection for OKF chunk embeddings.

Responsibilities (Phase 1 only):
  - Open/create a persistent Chroma collection under `vector_db/`.
  - Upsert embedded chunks (id = chunk_id, document = content, metadata = the
    remaining OKF fields, embedding = precomputed vector).
  - Query Top-K nearest neighbors for a given query vector.
  - Report basic collection stats.

This wrapper is deliberately isolated from the rest of the system so a future
MCP tool (or any other caller) can reuse it without changes. It does NOT embed
text itself — callers pass in precomputed vectors — keeping embedding and
storage concerns separate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb

from embedding_service.config import EMBEDDING_DIMENSION
from embedding_service.models import EmbeddedChunk
from vector_service.config import (
    COLLECTION_NAME,
    DEFAULT_TOP_K,
    DEFAULT_VECTOR_DB_DIR,
    DISTANCE_SPACE,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Metadata fields persisted alongside each vector (everything except the raw
# content, which is stored as the Chroma "document", and the embedding itself).
_METADATA_FIELDS = ("document_id", "title", "heading", "source_path")


@dataclass
class VectorSearchResult:
    """A single Top-K search hit returned from Chroma."""

    rank: int
    distance: float
    chunk_id: str
    document_id: str
    title: str
    heading: Optional[str]
    source_path: str
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "distance": self.distance,
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "title": self.title,
            "heading": self.heading,
            "source_path": self.source_path,
            "text": self.text,
        }


class ChromaStore:
    """Persistent Chroma-backed store for OKF chunk embeddings."""

    def __init__(
        self,
        db_dir: Optional[Path] = None,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        if db_dir is None:
            db_dir = PROJECT_ROOT / DEFAULT_VECTOR_DB_DIR
        self.db_dir = Path(db_dir).resolve()
        self.collection_name = collection_name
        self._client: Optional[chromadb.api.ClientAPI] = None
        self._collection = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _get_collection(self):
        if self._collection is None:
            self.db_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.db_dir))
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": DISTANCE_SPACE},
            )
            logger.info(
                "Opened Chroma collection '%s' at %s",
                self.collection_name,
                self.db_dir,
            )
        return self._collection

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_embedded_chunks(self, chunks: List[EmbeddedChunk]) -> int:
        """
        Upsert a batch of embedded chunks into the collection.

        Uses `chunk_id` as the primary key, so re-importing the same chunks
        updates them in place (idempotent) rather than duplicating.
        Returns the number of chunks written.
        """
        if not chunks:
            return 0

        collection = self._get_collection()
        ids = [c.chunk_id for c in chunks]
        documents = [c.content for c in chunks]
        embeddings = [c.embedding for c in chunks]
        metadatas = [
            {
                # Chroma metadata values must be non-null scalars; coerce None
                # (e.g. a missing heading) to an empty string.
                field: (getattr(c, field) if getattr(c, field) is not None else "")
                for field in _METADATA_FIELDS
            }
            for c in chunks
        ]

        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info("Upserted %d chunks into '%s'", len(ids), self.collection_name)
        return len(ids)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query(
        self,
        query_vector: List[float],
        top_k: int = DEFAULT_TOP_K,
    ) -> List[VectorSearchResult]:
        """Return the Top-K nearest chunks for a precomputed query vector."""
        if not query_vector:
            return []

        collection = self._get_collection()
        count = collection.count()
        if count == 0:
            return []

        n_results = min(top_k, count)
        raw = collection.query(
            query_embeddings=[query_vector],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        ids = raw.get("ids", [[]])[0]
        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        results: List[VectorSearchResult] = []
        for rank, (chunk_id, doc, meta, dist) in enumerate(
            zip(ids, documents, metadatas, distances), start=1
        ):
            meta = meta or {}
            heading = meta.get("heading") or None
            results.append(
                VectorSearchResult(
                    rank=rank,
                    distance=float(dist),
                    chunk_id=chunk_id,
                    document_id=meta.get("document_id", ""),
                    title=meta.get("title", ""),
                    heading=heading,
                    source_path=meta.get("source_path", ""),
                    text=doc or "",
                )
            )
        return results

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return basic information about the collection."""
        collection = self._get_collection()
        return {
            "collection_name": self.collection_name,
            "count": collection.count(),
            "persist_dir": str(self.db_dir),
            "distance_space": DISTANCE_SPACE,
            "embedding_dimension": EMBEDDING_DIMENSION,
        }
