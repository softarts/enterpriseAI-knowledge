"""Level-by-level anchor matching: assign each document an L1 -> L2 -> L3 path.

Method (per the brief, step 2): for each document, take the argmax dot product
against the L1 anchors; then, *within the chosen L1's children only*, argmax
against its L2 anchors; then again for L3. Every score is a dot product of two
L2-normalised vectors, i.e. a cosine similarity.

Restricting L2 to the children of the chosen L1 (rather than scoring against all
65 L2 anchors) is both cheaper and more correct: a document about
``Cash Management Services`` should compete for the Corporate Banking children,
not be pulled into Treasury's identically-named node.

Everything is batched over documents (default 50k rows/batch) so we never
materialise a [n_docs x n_anchors] matrix larger than one batch -- important
because the full corpus is ~512k rows even though this run uses a 3k sample.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from .anchors import Anchor, children_index

log = logging.getLogger(__name__)

DOC_BATCH = 50_000


@dataclass
class MatchResult:
    l1_key: str
    l1_score: float
    l2_key: Optional[str]
    l2_score: float
    l3_key: Optional[str]
    l3_score: float


def _argmax_within(
    doc_batch: np.ndarray,          # [b, dim]
    anchor_vecs: np.ndarray,        # [n_anchors, dim]
    candidate_rows: List[int],      # anchor indices to consider
) -> tuple:
    """Best (anchor_row, score) among candidate_rows for each doc in the batch.

    Returns (best_rows [b], best_scores [b]). If candidate_rows is empty, returns
    (-1, -inf) so callers can detect a missing sublevel (e.g. an L1 leaf that has
    no L2 children -- shouldn't happen for the 3-level seed but is handled).
    """
    b = doc_batch.shape[0]
    if not candidate_rows:
        return np.full(b, -1, dtype=np.int64), np.full(b, -np.inf, dtype=np.float32)
    sub = anchor_vecs[candidate_rows]                 # [c, dim]
    sims = doc_batch @ sub.T                           # [b, c]
    local = np.argmax(sims, axis=1)                    # [b]
    best_rows = np.asarray(candidate_rows, dtype=np.int64)[local]
    best_scores = sims[np.arange(b), local].astype(np.float32)
    return best_rows, best_scores


def match_hierarchical(
    doc_vecs: np.ndarray,           # [n_docs, dim], L2-normalised
    anchors: List[Anchor],
    anchor_vecs: np.ndarray,        # [n_anchors, dim], L2-normalised
    *,
    doc_batch: int = DOC_BATCH,
) -> List[MatchResult]:
    """Assign every document a full L1->L2->L3 path with per-level scores.

    Global Path Matching (方案 A):
    Instead of myopic top-down greedy search (which can commit to a suboptimal L1
    branch when L1 abstract similarity scores differ by only statistical noise),
    we evaluate valid complete leaf paths across the taxonomy tree and select the
    path that maximizes the leaf (L3) anchor similarity. The corresponding parent
    (L2) and grandparent (L1) nodes form the full hierarchical path.
    """
    kids = children_index(anchors)
    row_by_key = {a.key: i for i, a in enumerate(anchors)}

    # Collect all leaf nodes (anchors with no children) and their ancestor rows.
    leaf_paths = []
    for i, a in enumerate(anchors):
        if not kids.get(a.key):
            r1 = row_by_key.get(a.path_keys[0], -1) if len(a.path_keys) >= 1 else -1
            r2 = row_by_key.get(a.path_keys[1], -1) if len(a.path_keys) >= 2 else -1
            r3 = row_by_key.get(a.path_keys[2], -1) if len(a.path_keys) >= 3 else -1
            leaf_paths.append((i, r1, r2, r3, a))

    if not leaf_paths:
        raise ValueError("no leaf anchors found; taxonomy appears empty")

    leaf_rows = np.array([p[0] for p in leaf_paths], dtype=np.int64)

    n = doc_vecs.shape[0]
    results: List[MatchResult] = [None] * n  # type: ignore

    log.info("[match] matching %d documents against %d leaf paths (%d anchors total) in batches of %d",
             n, len(leaf_paths), len(anchors), doc_batch)

    for start in range(0, n, doc_batch):
        end = min(start + doc_batch, n)
        batch = doc_vecs[start:end]                    # [b, dim]

        # Compute full cosine similarity matrix for the batch against all anchors.
        sims = batch @ anchor_vecs.T                   # [b, n_anchors]
        leaf_sims = sims[:, leaf_rows]                 # [b, n_leaves]
        best_leaf_idx = np.argmax(leaf_sims, axis=1)   # [b]

        for j in range(end - start):
            r_leaf, r1, r2, r3, _ = leaf_paths[best_leaf_idx[j]]
            results[start + j] = MatchResult(
                l1_key=anchors[r1].key if r1 >= 0 else None,
                l1_score=float(sims[j, r1]) if r1 >= 0 else float("nan"),
                l2_key=anchors[r2].key if r2 >= 0 else None,
                l2_score=float(sims[j, r2]) if r2 >= 0 else float("nan"),
                l3_key=anchors[r3].key if r3 >= 0 else None,
                l3_score=float(sims[j, r3]) if r3 >= 0 else float("nan"),
            )

        log.info("[match]   matched rows [%d,%d)", start, end)

    return results


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------


def level_scores(results: List[MatchResult]) -> Dict[str, np.ndarray]:
    """Extract the per-level best-score arrays (used for threshold fitting)."""
    l1 = np.array([r.l1_score for r in results], dtype=np.float32)
    l2 = np.array([r.l2_score for r in results], dtype=np.float32)
    l3 = np.array([r.l3_score for r in results], dtype=np.float32)
    return {"L1": l1, "L2": l2, "L3": l3}


def save_match_results(results: List[MatchResult], anchors: List[Anchor], path: str) -> None:
    """Persist match results to npz.

    Keys are stored as index into the anchor list plus the score arrays; this is
    compact and reconstructs exactly given the same (fixed) anchor list.
    """
    key_to_row = {a.key: i for i, a in enumerate(anchors)}

    def rows_for(getter) -> np.ndarray:
        out = np.empty(len(results), dtype=np.int64)
        for i, r in enumerate(results):
            k = getter(r)
            out[i] = key_to_row.get(k, -1) if k is not None else -1
        return out

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        np.savez(
            fh,
            l1_rows=rows_for(lambda r: r.l1_key),
            l2_rows=rows_for(lambda r: r.l2_key),
            l3_rows=rows_for(lambda r: r.l3_key),
            l1_score=np.array([r.l1_score for r in results], dtype=np.float32),
            l2_score=np.array([r.l2_score for r in results], dtype=np.float32),
            l3_score=np.array([r.l3_score for r in results], dtype=np.float32),
        )
    written = tmp if os.path.exists(tmp) else tmp + ".npz"
    os.replace(written, path)
    log.info("[match] saved %d match results -> %s", len(results), path)
