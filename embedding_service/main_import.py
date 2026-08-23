"""
Batch import raw documents directly to chunks and embeddings.

Converts raw documents (TXT/Markdown/PDF/DOCX/HTML) into heading-aware chunks,
computes embeddings using LocalEmbedder, and persists them to embedding/ mirroring
the original folder structure.
"""

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from doc_service.retrieval.chunker import Chunk, chunk_document
from embedding_service.config import DEFAULT_EMBEDDING_DIR
from embedding_service.embedder import LocalEmbedder
from embedding_service.models import EmbeddedChunk
from embedding_service.storage import save_embeddings_to_json
from import_raw_doc_to_okf import (
    detect_file_type,
    extract_text,
    extract_title,
    normalize_txt_structure,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("embedding_importer")

RAW_ROOT_CANDIDATES = ["all_documents", "raw_documents", "documents"]


def resolve_input_root(input_path: Path) -> Path:
    """
    Automatically detect the root directory from input_path.
    If input_path contains one of RAW_ROOT_CANDIDATES, the candidate directory
    is treated as input_root so that subfolder hierarchy is mirrored.
    Otherwise falls back to input_path.parent (for files) or input_path (for dirs).
    """
    for part_name in RAW_ROOT_CANDIDATES:
        if part_name in input_path.parts:
            idx = input_path.parts.index(part_name)
            return Path(*input_path.parts[: idx + 1])

    if input_path.is_file() or input_path.suffix:
        return input_path.parent
    return input_path


def compute_document_id(file_path: Path, input_root: Path, mirror: bool) -> str:
    """
    Compute canonical document_id matching OKF and doc_service standards.
    """
    if mirror:
        try:
            relative = file_path.relative_to(input_root)
        except ValueError:
            relative = Path(file_path.name)
    else:
        relative = Path(file_path.name)

    stem = str(relative.with_suffix(""))
    doc_id = stem.replace("\\", "/").replace("/", "-").replace("_", "-")
    doc_id = re.sub(r"-+", "-", doc_id).lower().strip("-")
    return doc_id


def compute_relative_source_path(file_path: Path, input_root: Path) -> str:
    """
    Compute source_path normalized relative to input_root with forward slashes.
    """
    try:
        rel = file_path.relative_to(input_root)
    except ValueError:
        rel = Path(file_path.name)
    return str(rel).replace("\\", "/")


def compute_output_path(
    file_path: Path,
    input_root: Path,
    output_dir: Path,
    mirror: bool,
) -> Path:
    """
    Calculate destination JSON path for embedding file.
    - mirror=True: retains directory tree under output_dir.
    - mirror=False: places file directly in output_dir.
    """
    if mirror:
        try:
            relative = file_path.relative_to(input_root)
        except ValueError:
            relative = Path(file_path.name)
        return (output_dir / relative).with_suffix(".json")
    else:
        return output_dir / f"{file_path.stem}.json"


def collect_supported_files(input_path: Path) -> List[Path]:
    """Collect all supported document files under input_path."""
    if input_path.is_file():
        if detect_file_type(input_path) is not None:
            return [input_path]
        return []

    collected: List[Path] = []
    for root, _dirs, filenames in os.walk(input_path):
        for filename in sorted(filenames):
            fp = Path(root) / filename
            if detect_file_type(fp) is not None:
                collected.append(fp)
    return collected


def process_raw_document(
    file_path: Path,
    input_root: Path,
    output_dir: Path,
    embedder: LocalEmbedder,
    mirror: bool,
) -> bool:
    """
    Parse raw document, generate chunks, compute embeddings, and save to JSON.
    """
    file_type = detect_file_type(file_path)
    if file_type is None:
        logger.warning("Skipping unsupported file type: %s", file_path)
        return False

    try:
        text = extract_text(file_path, file_type)
        if not text.strip():
            logger.warning("Empty content in file: %s", file_path)
            return False

        if file_type == "text":
            text = normalize_txt_structure(text)

        title = extract_title(text, file_path)
        document_id = compute_document_id(file_path, input_root, mirror)
        source_path = compute_relative_source_path(file_path, input_root)

        # Chunk using heading-aware chunker
        chunks: List[Chunk] = chunk_document(
            document_id=document_id,
            title=title,
            content=text,
            source_path=source_path,
        )

        if not chunks:
            logger.warning("No chunks generated for: %s", file_path)
            return False

        # Embed all chunk texts
        texts_to_embed = [
            f"{c.title}\n{c.heading or ''}\n{c.content}".strip()
            for c in chunks
        ]
        vectors = embedder.embed_texts(texts_to_embed)

        # Assemble EmbeddedChunk models
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

        # Compute output target and save
        dest_json_path = compute_output_path(file_path, input_root, output_dir, mirror)
        save_embeddings_to_json(embedded_chunks, dest_json_path)
        logger.info("Successfully embedded [%s] (%d chunks) -> %s", document_id, len(chunks), dest_json_path)
        return True

    except Exception as e:
        logger.error("Failed to process document %s: %s", file_path, e, exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Batch convert raw documents into chunks + embeddings with local persistence."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input raw file or directory path (e.g. all_documents/confluence/...)",
    )
    parser.add_argument(
        "--output",
        required=False,
        default=None,
        help="Custom output directory (default: embedding/ with mirrored paths)",
    )

    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        logger.error("Input path does not exist: %s", input_path)
        sys.exit(1)

    input_root = resolve_input_root(input_path)

    if args.output is not None:
        output_dir = Path(args.output).resolve()
        mirror = False
    else:
        output_dir = (PROJECT_ROOT / DEFAULT_EMBEDDING_DIR).resolve()
        mirror = True

    files = collect_supported_files(input_path)
    if not files:
        logger.warning("No supported files found under: %s", input_path)
        sys.exit(0)

    logger.info("Found %d file(s) to process. Input root: %s, Output dir: %s, Mirror: %s", len(files), input_root, output_dir, mirror)

    embedder = LocalEmbedder()

    success_count = 0
    fail_count = 0

    for fp in files:
        ok = process_raw_document(
            file_path=fp,
            input_root=input_root,
            output_dir=output_dir,
            embedder=embedder,
            mirror=mirror,
        )
        if ok:
            success_count += 1
        else:
            fail_count += 1

    logger.info("=" * 60)
    logger.info("Embedding batch completed: %d succeeded, %d failed out of %d files.", success_count, fail_count, len(files))
    logger.info("Output location: %s", output_dir)
    logger.info("=" * 60)

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
