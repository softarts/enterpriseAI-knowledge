"""
Vector service CLI (Phase 1): Embedding -> Chroma -> Vector Search.

Two subcommands:

  Search the Chroma collection with a natural-language query:
      python -m vector_service.cli search "your question here"
      python -m vector_service.cli search "your question" --top-k 10

  Inspect the collection (row count and basic info):
      python -m vector_service.cli stats

The search flow: the query text is embedded with the SAME local model used at
import time (LocalEmbedder), then the query vector is sent to Chroma which
returns the Top-K nearest chunks with their distance, text, and metadata.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is importable when run as a script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from embedding_service.embedder import LocalEmbedder
from vector_service.chroma_store import ChromaStore
from vector_service.config import DEFAULT_TOP_K, DEFAULT_VECTOR_DB_DIR


def _resolve_db_dir(db_dir_arg: str | None) -> Path:
    if db_dir_arg:
        return Path(db_dir_arg).resolve()
    return (PROJECT_ROOT / DEFAULT_VECTOR_DB_DIR).resolve()


def cmd_search(args: argparse.Namespace) -> int:
    store = ChromaStore(db_dir=_resolve_db_dir(args.db_dir))

    info = store.stats()
    if info["count"] == 0:
        print(
            "Chroma collection is empty. Import first with:\n"
            "  python embedding_service/main_import.py --vector-db",
            file=sys.stderr,
        )
        return 1

    embedder = LocalEmbedder()
    query_vector = embedder.embed_query(args.query)

    results = store.query(query_vector, top_k=args.top_k)

    print()
    print("=" * 70)
    print(f"QUERY: {args.query}")
    print(f"Collection: {info['collection_name']}  (count={info['count']}, "
          f"space={info['distance_space']})")
    print("=" * 70)
    if not results:
        print("No results.")
        return 0

    for r in results:
        heading = r.heading if r.heading else "(none)"
        print()
        print(f"[{r.rank}] distance={r.distance:.4f}")
        print(f"    chunk_id:    {r.chunk_id}")
        print(f"    document_id: {r.document_id}")
        print(f"    title:       {r.title}")
        print(f"    heading:     {heading}")
        print(f"    source_path: {r.source_path}")
        text = r.text if len(r.text) <= 500 else r.text[:500] + " ...[truncated]"
        print("    text:")
        for line in text.splitlines():
            print(f"      {line}")
    print()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    store = ChromaStore(db_dir=_resolve_db_dir(args.db_dir))
    info = store.stats()

    print()
    print("=" * 70)
    print("CHROMA COLLECTION STATS")
    print("=" * 70)
    print(f"  collection_name:     {info['collection_name']}")
    print(f"  count (records):     {info['count']}")
    print(f"  persist_dir:         {info['persist_dir']}")
    print(f"  distance_space:      {info['distance_space']}")
    print(f"  embedding_dimension: {info['embedding_dimension']}")
    print()
    if info["count"] == 0:
        print("Collection is empty. Import with: "
              "python embedding_service/main_import.py --vector-db")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chroma vector store CLI (Phase 1): search and stats."
    )
    parser.add_argument(
        "--db-dir",
        dest="db_dir",
        default=None,
        help=f"Chroma persistent dir (default: {DEFAULT_VECTOR_DB_DIR}/).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="Search the collection with a query.")
    p_search.add_argument("query", type=str, help="Natural-language query.")
    p_search.add_argument(
        "--top-k",
        dest="top_k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Number of results (default: {DEFAULT_TOP_K}).",
    )
    p_search.set_defaults(func=cmd_search)

    p_stats = sub.add_parser("stats", help="Show collection stats.")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
