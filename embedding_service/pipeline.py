"""Service API for OKF -> chunks -> embeddings -> vector store."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from document_import import OKFDocument, parse_okf_file
from .chunker import chunk_document
from .embedder import Embedder, get_embedder
from .models import EmbeddedChunk


@dataclass(frozen=True)
class EmbeddingPipelineResult:
    document_id: str
    model: str
    chunk_count: int
    dimension: int


class EmbeddingPipelineService:
    """Process OKF documents without requiring the legacy importer CLI."""

    def __init__(self, model: Optional[str] = None, embedder: Optional[Embedder] = None,
                 vector_store: Optional[Any] = None):
        self.embedder = embedder or get_embedder(model)
        self.vector_store = vector_store

    def process_okf_file(self, file_path: Path) -> EmbeddingPipelineResult:
        return self.process_document(parse_okf_file(Path(file_path)))

    def process_document(self, document: OKFDocument) -> EmbeddingPipelineResult:
        chunks = chunk_document(document_id=document.document_id, title=document.title,
                                 content=document.content, source_path=document.source_path,
                                 version=getattr(document, "version", None))
        texts = [f"{chunk.title}\n{' > '.join(chunk.heading_path)}\n{chunk.content}".strip() for chunk in chunks]
        vectors = self.embedder.embed_documents(texts)
        if len(vectors) != len(chunks) or any(len(vector) != self.embedder.dimension for vector in vectors):
            raise ValueError(f"Embedding dimension mismatch for {self.embedder.model_name}")
        embedded = [EmbeddedChunk(
            chunk_id=chunk.chunk_id, document_id=chunk.document_id, title=chunk.title,
            heading=chunk.heading, content=chunk.content, source_path=chunk.source_path,
            embedding=vector, version=chunk.version, chunk_index=chunk.chunk_index,
            heading_path=chunk.heading_path, content_hash=chunk.content_hash,
            token_count=chunk.token_count, chunk_version=chunk.chunk_version,
            embedding_model=self.embedder.model_name, embedding_dimension=len(vector),
            normalized=self.embedder.normalize_embeddings, offsets=chunk.offsets,
        ) for chunk, vector in zip(chunks, vectors)]
        if self.vector_store is not None:
            self.vector_store.add_embedded_chunks(embedded)
        return EmbeddingPipelineResult(document.document_id, self.embedder.model_name,
                                       len(embedded), self.embedder.dimension)
