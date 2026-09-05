"""
Retrieval Evaluation Script.

Evaluates the semantic retrieval performance of persisted OKF embeddings
and Cosine Similarity against a curated evaluation query dataset.
Computes Hit@1, Hit@3, Hit@5, and MRR metrics with detailed error analysis.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from embedding_service.config import DEFAULT_EMBEDDING_DIR
from embedding_service.embedder import get_embedder
from embedding_service.models import EmbeddedChunk
from embedding_service.search import SimilarityResult, search_by_similarity
from embedding_service.storage import load_all_embeddings

DEFAULT_EVAL_PATH = Path(__file__).resolve().parent / "evaluation_queries.json"


@dataclass
class QueryEvalResult:
    """Evaluation result for a single query."""

    query_id: str
    query_text: str
    category: str
    difficulty: str
    expected_document_id: str
    expected_source_path: str
    expected_heading: Optional[str]
    expected_chunk_ids: List[str]
    top_results: List[SimilarityResult]
    hit_rank: Optional[int]
    hit_at_1: bool
    hit_at_3: bool
    hit_at_5: bool
    reciprocal_rank: float


def resolve_ground_truth_chunks(
    query_item: Dict[str, Any],
    all_chunks: List[EmbeddedChunk],
) -> Set[str]:
    """
    Resolve matching chunk IDs for a query item based on ground-truth criteria.
    Supports:
      - expected_chunk_id / relevant_chunk_ids
      - expected_document_id + expected_heading
      - acceptable_documents (list of {document_id, heading})
    """
    matching_chunk_ids: Set[str] = set()

    exp_chunk = query_item.get("expected_chunk_id")
    rel_chunks = query_item.get("relevant_chunk_ids", [])
    exp_doc = query_item.get("expected_document_id")
    exp_heading = query_item.get("expected_heading")
    acceptable_docs = query_item.get("acceptable_documents", [])

    for chunk in all_chunks:
        is_match = False

        # 1. Direct chunk ID match
        if exp_chunk and chunk.chunk_id == exp_chunk:
            is_match = True
        elif rel_chunks and chunk.chunk_id in rel_chunks:
            is_match = True

        # 2. Expected document_id + heading match
        elif exp_doc and chunk.document_id == exp_doc:
            if not exp_heading:
                is_match = True
            elif chunk.heading == exp_heading:
                is_match = True
            elif exp_heading in chunk.content:
                is_match = True
            elif chunk.heading and exp_heading in chunk.heading:
                is_match = True

        # 3. Acceptable documents match
        if not is_match and acceptable_docs:
            for acc in acceptable_docs:
                acc_doc = acc.get("document_id")
                acc_heading = acc.get("heading")
                if acc_doc and chunk.document_id == acc_doc:
                    if not acc_heading:
                        is_match = True
                    elif chunk.heading == acc_heading:
                        is_match = True
                    elif acc_heading in chunk.content:
                        is_match = True
                    elif chunk.heading and acc_heading in chunk.heading:
                        is_match = True

        if is_match:
            matching_chunk_ids.add(chunk.chunk_id)

    return matching_chunk_ids


def evaluate_retrieval(
    eval_path: Path,
    embedding_dir: Path,
    top_k: int = 5,
) -> List[QueryEvalResult]:
    """
    Run retrieval evaluation across all queries in the dataset.
    """
    if not eval_path.exists():
        raise FileNotFoundError(f"Evaluation dataset file not found: {eval_path}")

    if not embedding_dir.exists():
        raise FileNotFoundError(f"Embedding directory not found: {embedding_dir}")

    with open(eval_path, "r", encoding="utf-8") as f:
        eval_data = json.load(f)

    queries: List[Dict[str, Any]] = eval_data.get("queries", [])
    if not queries:
        raise ValueError(f"No queries found in {eval_path}")

    all_chunks: List[EmbeddedChunk] = load_all_embeddings(embedding_dir)
    if not all_chunks:
        raise ValueError(f"No embedded chunks loaded from {embedding_dir}")

    embedder = get_embedder()

    print("=" * 60)
    print("Retrieval Evaluation")
    print("=" * 60)
    print(f"Evaluation dataset: {eval_path.name}")
    print(f"Total queries: {len(queries)}")
    print(f"Available chunks: {len(all_chunks)}")
    print()

    eval_results: List[QueryEvalResult] = []

    for idx, q in enumerate(queries, start=1):
        query_id = q.get("id", f"Q{idx:03d}")
        query_text = q.get("query", "")
        category = q.get("category", "unknown")
        difficulty = q.get("difficulty", "medium")
        exp_doc = q.get("expected_document_id", "")
        exp_source = q.get("expected_source_path", "")
        exp_heading = q.get("expected_heading", "")

        # Find matching chunk IDs
        matching_chunks = resolve_ground_truth_chunks(q, all_chunks)

        # Compute query vector and perform similarity search
        query_vector = embedder.embed_query(query_text)
        top_results = search_by_similarity(query_vector, all_chunks, top_k=top_k)

        # Determine first rank of a ground-truth match
        hit_rank: Optional[int] = None
        for rank, res in enumerate(top_results, start=1):
            if res.chunk_id in matching_chunks:
                hit_rank = rank
                break

        hit_1 = hit_rank == 1
        hit_3 = hit_rank is not None and hit_rank <= 3
        hit_5 = hit_rank is not None and hit_rank <= 5
        rr = (1.0 / hit_rank) if hit_rank is not None else 0.0

        eval_results.append(
            QueryEvalResult(
                query_id=query_id,
                query_text=query_text,
                category=category,
                difficulty=difficulty,
                expected_document_id=exp_doc,
                expected_source_path=exp_source,
                expected_heading=exp_heading,
                expected_chunk_ids=sorted(list(matching_chunks)),
                top_results=top_results,
                hit_rank=hit_rank,
                hit_at_1=hit_1,
                hit_at_3=hit_3,
                hit_at_5=hit_5,
                reciprocal_rank=rr,
            )
        )

        # Print per-query evaluation details
        print("-" * 60)
        print(f"Query {idx}: {query_id} [{category}] ({difficulty})")
        print("-" * 60)
        print(f"Query: {query_text}")
        print()
        print("Expected:")
        print(f"  document_id: {exp_doc}")
        if exp_heading:
            print(f"  heading:     {exp_heading}")
        print(f"  chunks:      {sorted(list(matching_chunks))}")
        print()
        print(f"Top {top_k}:")
        for r_idx, res in enumerate(top_results, start=1):
            is_match_flag = " [HIT]" if res.chunk_id in matching_chunks else ""
            h_text = f" | {res.heading}" if res.heading else ""
            print(f"  {r_idx}. score={res.score:.4f}  chunk={res.chunk_id}{h_text}{is_match_flag}")
        print()
        print("Result:")
        print(f"  Hit@1: {'YES' if hit_1 else 'NO'}")
        print(f"  Hit@3: {'YES' if hit_3 else 'NO'}")
        print(f"  Hit@5: {'YES' if hit_5 else 'NO'}")
        print(f"  Reciprocal Rank: {rr:.4f} (Rank: {hit_rank if hit_rank is not None else 'None'})")
        print()

    # Compute overall metrics
    total_q = len(eval_results)
    avg_hit_1 = sum(1 for r in eval_results if r.hit_at_1) / total_q
    avg_hit_3 = sum(1 for r in eval_results if r.hit_at_3) / total_q
    avg_hit_5 = sum(1 for r in eval_results if r.hit_at_5) / total_q
    avg_mrr = sum(r.reciprocal_rank for r in eval_results) / total_q

    print("=" * 60)
    print("Overall Results")
    print("=" * 60)
    print(f"Queries: {total_q}")
    print()
    print(f"Hit@1:  {avg_hit_1:.4f} ({sum(1 for r in eval_results if r.hit_at_1)}/{total_q})")
    print(f"Hit@3:  {avg_hit_3:.4f} ({sum(1 for r in eval_results if r.hit_at_3)}/{total_q})")
    print(f"Hit@5:  {avg_hit_5:.4f} ({sum(1 for r in eval_results if r.hit_at_5)}/{total_q})")
    print(f"MRR:    {avg_mrr:.4f}")
    print()

    # Category breakdown
    categories = sorted(list(set(r.category for r in eval_results)))
    print("Breakdown by Category:")
    for cat in categories:
        cat_results = [r for r in eval_results if r.category == cat]
        cat_n = len(cat_results)
        cat_h1 = sum(1 for r in cat_results if r.hit_at_1) / cat_n
        cat_h3 = sum(1 for r in cat_results if r.hit_at_3) / cat_n
        cat_h5 = sum(1 for r in cat_results if r.hit_at_5) / cat_n
        cat_mrr = sum(r.reciprocal_rank for r in cat_results) / cat_n
        print(
            f"  - {cat:16s} (n={cat_n}): Hit@1={cat_h1:.2f}, Hit@3={cat_h3:.2f}, Hit@5={cat_h5:.2f}, MRR={cat_mrr:.4f}"
        )
    print("=" * 60)

    # Error analysis for misses
    missed_queries = [r for r in eval_results if not r.hit_at_5]
    if missed_queries:
        print("\n" + "=" * 60)
        print(f"Error Analysis (Misses at Top-{top_k}: {len(missed_queries)} query/queries)")
        print("=" * 60)
        for m in missed_queries:
            print(f"\n[MISS] {m.query_id}: {m.query_text}")
            print(f"  Category:        {m.category}")
            print(f"  Difficulty:      {m.difficulty}")
            print(f"  Expected Doc:    {m.expected_document_id}")
            print(f"  Expected Head:   {m.expected_heading}")
            print(f"  Expected Chunks: {m.expected_chunk_ids}")
            print(f"  Top-{top_k} Actual Retrieved:")
            for r_idx, res in enumerate(m.top_results, start=1):
                print(
                    f"    {r_idx}. score={res.score:.4f} | chunk={res.chunk_id}\n"
                    f"       title:       {res.title}\n"
                    f"       heading:     {res.heading}\n"
                    f"       source_path: {res.source_path}"
                )
        print("=" * 60)
    else:
        print(f"\nAll {total_q} queries successfully retrieved within Top-{top_k}!")

    return eval_results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate embedding retrieval quality on OKF evaluation dataset."
    )
    parser.add_argument(
        "--eval",
        dest="eval_path",
        type=Path,
        default=DEFAULT_EVAL_PATH,
        help=f"Path to evaluation queries JSON (default: {DEFAULT_EVAL_PATH})",
    )
    parser.add_argument(
        "--embedding-dir",
        dest="embedding_dir",
        type=Path,
        default=Path(DEFAULT_EMBEDDING_DIR),
        help=f"Directory containing persisted embedding JSON files (default: {DEFAULT_EMBEDDING_DIR})",
    )
    parser.add_argument(
        "--top-k",
        dest="top_k",
        type=int,
        default=5,
        help="Top-K cutoff for evaluation metrics (default: 5)",
    )

    args = parser.parse_args()
    evaluate_retrieval(
        eval_path=args.eval_path,
        embedding_dir=args.embedding_dir,
        top_k=args.top_k,
    )


if __name__ == "__main__":
    main()
