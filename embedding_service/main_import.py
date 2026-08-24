"""
Batch import OKF documents directly to chunks and embeddings.

Reads standardized OKF documents (Markdown + YAML frontmatter in generated/),
generates heading-aware chunks using existing chunker, computes embeddings
using LocalEmbedder, and persists them to embedding/ mirroring the generated/
folder structure.
"""

import argparse
import logging
import os
from pathlib import Path
from typing import List, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from doc_service.repositories.okf_document_repository import OKFDocumentRepository
from doc_service.retrieval.chunker import Chunk, chunk_document
from embedding_service.config import DEFAULT_EMBEDDING_DIR, DEFAULT_OKF_DIR
from embedding_service.embedder import LocalEmbedder
from embedding_service.models import EmbeddedChunk
from embedding_service.storage import save_embeddings_to_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("embedding_importer")

OKF_ROOT_CANDIDATES = ["generated", "okf", "okf_documents"]


def resolve_input_root(input_path: Path) -> Path:
    """
    Automatically detect the root directory from input_path.
    If input_path contains one of OKF_ROOT_CANDIDATES (e.g. generated),
    that directory is treated as input_root so that subfolder hierarchy is mirrored.
    Otherwise falls back to input_path (if directory) or input_path.parent (if file).
    """
    for part_name in OKF_ROOT_CANDIDATES:
        if part_name in input_path.parts:
            idx = input_path.parts.index(part_name)
            return Path(*input_path.parts[: idx + 1])

    if input_path.is_file() or input_path.suffix:
        return input_path.parent
    return input_path


def compute_output_path(
    file_path: Path,
    input_root: Path,
    output_dir: Path,
    mirror: bool = True,
) -> Path:
    """
    Calculate destination JSON path for embedding file.
    - mirror=True: retains directory tree under output_dir relative to input_root.
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


def collect_okf_files(input_path: Path) -> List[Path]:
    """Collect all OKF (.yaml, .yml) files under input_path."""
    if input_path.is_file():
        if input_path.suffix.lower() in [".yaml", ".yml"]:
            return [input_path]
        return []

    collected: List[Path] = []
    for root, _dirs, filenames in os.walk(input_path):
        for filename in sorted(filenames):
            fp = Path(root) / filename
            if fp.suffix.lower() in [".yaml", ".yml"]:
                collected.append(fp)
    return collected


def process_okf_document(
    file_path: Path,
    input_root: Path,
    output_dir: Path,
    embedder: LocalEmbedder,
    mirror: bool = True,
) -> bool:
    """
    Parse an OKF document, generate chunks, compute embeddings, and save to JSON.
    Uses existing OKF repository parser and heading-aware chunker.
    Inherits document_id, title, source_path, and heading directly from OKF metadata.
    """
    if file_path.suffix.lower() not in [".yaml", ".yml"]:
        logger.warning("Skipping non-OKF file: %s", file_path)
        return False

    try:
        repo = OKFDocumentRepository(okf_dir=input_root)
        record = repo._parse_okf_file(file_path)
        if not record:
            logger.warning("Failed to parse OKF document: %s", file_path)
            return False

        # Chunk using heading-aware chunker
        chunks: List[Chunk] = chunk_document(
            document_id=record.document_id,
            title=record.title,
            content=record.content,
            source_path=record.source_path,
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
        logger.info("Successfully embedded [%s] (%d chunks) -> %s", record.document_id, len(chunks), dest_json_path)
        return True

    except Exception as e:
        logger.error("Failed to process OKF document %s: %s", file_path, e, exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Batch import OKF documents (from generated/) into chunks + embeddings with local persistence."
    )
    parser.add_argument(
        "--input",
        required=False,
        default=str(PROJECT_ROOT / DEFAULT_OKF_DIR),
        help="Input OKF file or directory path (default: generated/)",
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

    files = collect_okf_files(input_path)
    if not files:
        logger.warning("No OKF files (.yaml, .yml) found under: %s", input_path)
        sys.exit(0)

    logger.info("Found %d OKF file(s) to process. Input root: %s, Output dir: %s, Mirror: %s", len(files), input_root, output_dir, mirror)

    embedder = LocalEmbedder()

    success_count = 0
    fail_count = 0

    for fp in files:
        ok = process_okf_document(
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
    logger.info("OKF embedding batch completed: %d succeeded, %d failed out of %d files.", success_count, fail_count, len(files))
    logger.info("Output location: %s", output_dir)
    logger.info("=" * 60)

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
