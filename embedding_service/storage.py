import json
import logging
from pathlib import Path
from typing import List

from embedding_service.models import EmbeddedChunk

logger = logging.getLogger(__name__)


def save_embeddings_to_json(
    embedded_chunks: List[EmbeddedChunk],
    destination_file: Path,
) -> None:
    """
    Save embedded chunks to a local JSON file.
    Creates parent directories if necessary.
    """
    destination_file.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "chunk_id": item.chunk_id,
            "document_id": item.document_id,
            "title": item.title,
            "heading": item.heading,
            "content": item.content,
            "source_path": item.source_path,
            "embedding": item.embedding,
            "version": item.version,
            "chunk_index": item.chunk_index,
            "heading_path": list(item.heading_path),
            "content_hash": item.content_hash,
            "token_count": item.token_count,
            "chunk_version": item.chunk_version,
            "embedding_model": item.embedding_model,
            "embedding_dimension": item.embedding_dimension,
            "normalized": item.normalized,
            "offsets": list(item.offsets) if item.offsets is not None else None,
            "document_metadata": item.document_metadata,
        }
        for item in embedded_chunks
    ]
    with open(destination_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("Saved %d embeddings to %s", len(embedded_chunks), destination_file)


def load_embeddings_from_json(file_path: Path) -> List[EmbeddedChunk]:
    """
    Load embedded chunks from a local JSON file.
    """
    if not file_path.exists():
        logger.warning("Embedding file does not exist: %s", file_path)
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks: List[EmbeddedChunk] = []
    for item in data:
        chunks.append(
            EmbeddedChunk(
                chunk_id=item["chunk_id"],
                document_id=item["document_id"],
                title=item["title"],
                heading=item.get("heading"),
                content=item["content"],
                source_path=item["source_path"],
                embedding=item["embedding"],
                version=item.get("version"),
                chunk_index=item.get("chunk_index", 0),
                heading_path=tuple(item.get("heading_path", ()) or ()),
                content_hash=item.get("content_hash", ""),
                token_count=item.get("token_count", 0),
                chunk_version=item.get("chunk_version", "v1"),
                embedding_model=item.get("embedding_model"),
                embedding_dimension=item.get("embedding_dimension"),
                normalized=item.get("normalized"),
                offsets=tuple(item["offsets"]) if item.get("offsets") is not None else None,
                document_metadata=item.get("document_metadata", {}),
            )
        )
    logger.info("Loaded %d embeddings from %s", len(chunks), file_path)
    return chunks


def load_all_embeddings(embedding_dir: Path) -> List[EmbeddedChunk]:
    """
    Recursively load all embedding JSON files from the embedding directory.
    """
    if not embedding_dir.exists():
        logger.warning("Embedding root directory does not exist: %s", embedding_dir)
        return []

    all_chunks: List[EmbeddedChunk] = []
    for json_file in sorted(embedding_dir.rglob("*.json")):
        chunks = load_embeddings_from_json(json_file)
        all_chunks.extend(chunks)
    logger.info("Loaded total %d embeddings from %s", len(all_chunks), embedding_dir)
    return all_chunks
