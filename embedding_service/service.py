import logging
from pathlib import Path
from typing import List, Optional


from doc_service.repositories.okf_document_repository import OKFDocumentRepository
from doc_service.retrieval.chunker import Chunk, chunk_document
from embedding_service.config import DEFAULT_EMBEDDING_DIR, DEFAULT_OKF_DIR
from embedding_service.embedder import LocalEmbedder
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
    Connects OKF parsing/chunking with LocalEmbedder and Storage.
    """

    def __init__(
        self,
        okf_dir: Path = Path(DEFAULT_OKF_DIR),
        embedding_dir: Path = Path(DEFAULT_EMBEDDING_DIR),
        embedder: LocalEmbedder = None,
    ) -> None:
        self.okf_dir = okf_dir
        self.embedding_dir = embedding_dir
        self.embedder = embedder or LocalEmbedder()
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
                source_path=doc.source_path,
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
                source_path=doc.source_path,
            )
            if not chunks:
                continue

            # Prepare text for embedding (incorporate title, heading and body content)
            texts_to_embed = [
                f"{c.title}\n{c.heading or ''}\n{c.content}".strip()
                for c in chunks
            ]
            vectors = self.embedder.embed_texts(texts_to_embed)

            doc_embedded_chunks: List[EmbeddedChunk] = []
            for chunk, vec in zip(chunks, vectors):
                embedded_chunk = EmbeddedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=chunk.title,
                    heading=chunk.heading,
                    content=chunk.content,
                    source_path=chunk.source_path,
                    embedding=vec,
                )
                doc_embedded_chunks.append(embedded_chunk)

            save_embeddings_to_json(doc_embedded_chunks, embedding_file_path)
            all_embedded_chunks.extend(doc_embedded_chunks)

        return all_embedded_chunks

    def embed_and_persist_raw_file(
        self,
        file_path: Path,
        input_root: Path,
        output_dir: Optional[Path] = None,
        mirror: bool = True,
    ) -> List[EmbeddedChunk]:
        """
        Embed and persist a single raw document directly.
        """
        from embedding_service.main_import import (
            compute_document_id,
            compute_output_path,
            compute_relative_source_path,
        )
        from import_raw_doc_to_okf import (
            detect_file_type,
            extract_text,
            extract_title,
            normalize_txt_structure,
        )

        out_dir = output_dir or self.embedding_dir
        file_type = detect_file_type(file_path)
        if not file_type:
            return []

        text = extract_text(file_path, file_type)
        if not text.strip():
            return []

        if file_type == "text":
            text = normalize_txt_structure(text)

        title = extract_title(text, file_path)
        document_id = compute_document_id(file_path, input_root, mirror)
        source_path = compute_relative_source_path(file_path, input_root)

        chunks = chunk_document(
            document_id=document_id,
            title=title,
            content=text,
            source_path=source_path,
        )
        if not chunks:
            return []

        texts_to_embed = [
            f"{c.title}\n{c.heading or ''}\n{c.content}".strip()
            for c in chunks
        ]
        vectors = self.embedder.embed_texts(texts_to_embed)

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
                    embedding=vec,
                )
            )

        dest_json_path = compute_output_path(file_path, input_root, out_dir, mirror)
        save_embeddings_to_json(embedded_chunks, dest_json_path)
        return embedded_chunks

    def load_all_persisted_embeddings(self) -> List[EmbeddedChunk]:
        """
        Load all persisted embeddings from embedding_dir.
        """
        return load_all_embeddings(self.embedding_dir)

