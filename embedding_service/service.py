import logging
from pathlib import Path
from typing import List, Optional


from doc_service.repositories.okf_document_repository import OKFDocumentRepository
from embedding_service.chunker import Chunk, chunk_document
from embedding_service.config import ACTIVE_MODEL, DEFAULT_EMBEDDING_DIR, DEFAULT_OKF_DIR
from embedding_service.embedder import Embedder, get_embedder
from embedding_service.models import EmbeddedChunk
from embedding_service.storage import (
    load_all_embeddings,
    load_embeddings_from_json,
    save_embeddings_to_json,
)

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Orchestration layer for embedding generation, persistence, and loading.
    Connects OKF parsing/chunking with the configured Embedder and Storage.
    """

    def __init__(
        self,
        okf_dir: Path = Path(DEFAULT_OKF_DIR),
        embedding_dir: Optional[Path] = None,
        embedder: Optional[Embedder] = None,
        model: Optional[str] = None,
    ) -> None:
        self.okf_dir = okf_dir
        self.embedder = embedder or get_embedder(model)
        self.embedding_dir = embedding_dir or (Path(DEFAULT_EMBEDDING_DIR) / (model or ACTIVE_MODEL))
        self.repo = OKFDocumentRepository(okf_dir=okf_dir)

    def get_embedding_path_for_okf(self, okf_file_path: Path) -> Path:
        """
        Compute the mirrored json path under embedding_dir for a given okf file path.
        Example: generated/sub/doc.yaml -> embedding/sub/doc.json
        """
        try:
            rel = okf_file_path.relative_to(self.okf_dir)
        except ValueError:
            rel = Path(okf_file_path.name)
        return (self.embedding_dir / rel).with_suffix(".json")

    def build_chunks_for_all_docs(self) -> List[Chunk]:
        """
        Scan all OKF documents and chunk them using the existing heading-aware chunker.
        """
        docs = self.repo.list_documents()
        all_chunks: List[Chunk] = []
        for doc in docs:
            chunks = chunk_document(
                document_id=doc.document_id,
                title=doc.title,
                content=doc.content,
                source_path=doc.source_path, version=getattr(doc, "version", None),
            )
            all_chunks.extend(chunks)
        return all_chunks

    def embed_and_persist_all(self) -> List[EmbeddedChunk]:
        """
        Load all OKF documents, chunk them, compute embeddings, and save each document's
        embedded chunks to its mirrored path under embedding/.
        """
        docs = self.repo.list_documents()
        all_embedded_chunks: List[EmbeddedChunk] = []

        for doc in docs:
            doc_file_path = Path(doc.file_path) if doc.file_path else self.okf_dir / f"{doc.document_id}.yaml"
            embedding_file_path = self.get_embedding_path_for_okf(doc_file_path)

            chunks = chunk_document(
                document_id=doc.document_id,
                title=doc.title,
                content=doc.content,
                source_path=doc.source_path, version=getattr(doc, "version", None),
            )
            if not chunks:
                continue

            # Prepare text for embedding (incorporate title, heading and body content)
            texts_to_embed = [
                f"{c.title}\n{' > '.join(c.heading_path)}\n{c.content}".strip()
                for c in chunks
            ]
            vectors = self.embedder.embed_documents(texts_to_embed)
            self._validate_vectors(vectors)

            doc_embedded_chunks: List[EmbeddedChunk] = []
            for chunk, vec in zip(chunks, vectors):
                embedded_chunk = EmbeddedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=chunk.title,
                    heading=chunk.heading,
                    content=chunk.content,
                    source_path=chunk.source_path,
                    embedding=vec, version=chunk.version, chunk_index=chunk.chunk_index,
                    heading_path=chunk.heading_path, content_hash=chunk.content_hash,
                    token_count=chunk.token_count, chunk_version=chunk.chunk_version,
                    embedding_model=self.embedder.model_name, embedding_dimension=len(vec),
                    normalized=self.embedder.normalize_embeddings, offsets=chunk.offsets,
                )
                doc_embedded_chunks.append(embedded_chunk)

            save_embeddings_to_json(doc_embedded_chunks, embedding_file_path)
            all_embedded_chunks.extend(doc_embedded_chunks)

        return all_embedded_chunks

    def embed_and_persist_okf_file(
        self,
        file_path: Path,
        input_root: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        mirror: bool = True,
    ) -> List[EmbeddedChunk]:
        """
        Embed and persist a single OKF document file.
        """
        in_root = input_root or self.okf_dir
        out_dir = output_dir or self.embedding_dir

        if file_path.suffix.lower() not in [".yaml", ".yml"]:
            return []

        repo = OKFDocumentRepository(okf_dir=in_root)
        record = repo._parse_okf_file(file_path)
        if not record:
            return []

        chunks = chunk_document(
            document_id=record.document_id,
            title=record.title,
            content=record.content,
            source_path=record.source_path, version=getattr(record, "version", None),
        )
        if not chunks:
            return []

        texts_to_embed = [
            f"{c.title}\n{' > '.join(c.heading_path)}\n{c.content}".strip()
            for c in chunks
        ]
        vectors = self.embedder.embed_documents(texts_to_embed)
        self._validate_vectors(vectors)

        embedded_chunks: List[EmbeddedChunk] = []
        for chunk, vec in zip(chunks, vectors):
            embedded_chunks.append(
                EmbeddedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=chunk.title,
                    heading=chunk.heading,
                    content=chunk.content,
                    source_path=chunk.source_path,
                    embedding=vec, version=chunk.version, chunk_index=chunk.chunk_index,
                    heading_path=chunk.heading_path, content_hash=chunk.content_hash,
                    token_count=chunk.token_count, chunk_version=chunk.chunk_version,
                    embedding_model=self.embedder.model_name, embedding_dimension=len(vec),
                    normalized=self.embedder.normalize_embeddings, offsets=chunk.offsets,
                )
            )

        if mirror:
            try:
                relative = file_path.relative_to(in_root)
            except ValueError:
                relative = Path(file_path.name)
            dest_json_path = (out_dir / relative).with_suffix(".json")
        else:
            dest_json_path = out_dir / f"{file_path.stem}.json"

        save_embeddings_to_json(embedded_chunks, dest_json_path)
        return embedded_chunks

    def _validate_vectors(self, vectors: List[List[float]]) -> None:
        expected = int(self.embedder.dimension)
        if any(len(vector) != expected for vector in vectors):
            raise ValueError(f"Embedding dimension mismatch: expected {expected}")

    def load_embeddings_from_file(self, file_path: Path) -> List[EmbeddedChunk]:
        """
        Load embedded chunks from a specific JSON file.
        """
        return load_embeddings_from_json(file_path)

    def load_embeddings_for_okf_docs(self) -> List[EmbeddedChunk]:
        """
        Load embedded chunks corresponding to all OKF documents in okf_dir.
        """
        docs = self.repo.list_documents()
        chunks: List[EmbeddedChunk] = []
        for doc in docs:
            doc_file_path = Path(doc.file_path) if doc.file_path else self.okf_dir / f"{doc.document_id}.yaml"
            embedding_file_path = self.get_embedding_path_for_okf(doc_file_path)
            if embedding_file_path.exists():
                chunks.extend(load_embeddings_from_json(embedding_file_path))
        return chunks

    def load_all_persisted_embeddings(self) -> List[EmbeddedChunk]:
        """
        Load all persisted embeddings from embedding_dir.
        """
        return load_all_embeddings(self.embedding_dir)
