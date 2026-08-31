"""Taxonomy classifier: per-article, rule-based classification (task 9.1).

Formerly ``stage_b``. This is the steady-state production API that classifies a
document (or a batch) at import time. It consumes the frozen Stage A artifacts
read-only:
  * a taxonomy -- by default the PINNED production version (see
    ``PINNED_TAXONOMY_VERSION`` below) so it does NOT drift as Stage A keeps
    generating new rounds; override with ``--taxonomy-version`` / the
    ``taxonomy_version`` argument;
  * ``config/thresholds.json`` (per-level L1/L2/L3 cosine thresholds).

For each document it runs the *same* hierarchical nearest-anchor matching used
in bootstrap (``common.matching.match_hierarchical``) and then applies the
thresholds level by level:

  * L1 score < threshold[L1]                -> status ``UNKNOWN`` (no path)
  * L1 ok, L2 score < threshold[L2]         -> path truncated at L1, status
                                               ``PARTIAL`` (assigned to L1 only)
  * L1, L2 ok, L3 score < threshold[L3]     -> path truncated at L2, ``PARTIAL``
  * all three >= threshold                  -> full L1>L2>L3 path, ``ASSIGNED``

No clustering, no LLM: each document is a handful of dot products, exactly the
cheap steady-state path the original brief specifies for Stage B. The output is
OKF-style metadata (three-level key/name path + per-level scores + status) that
downstream RAG can use for metadata-filtered hybrid retrieval.

CLI
---
  # one document from stdin/args
  python -m kb_classifier.taxonomy_classifier.classify text --title "..." --body "..."

  # one document from a file (first non-empty line = title, rest = body)
  python -m kb_classifier.taxonomy_classifier.classify file path/to/doc.txt

  # batch: classify every article under all_documents/ -> jsonl of doc_id->path
  python -m kb_classifier.taxonomy_classifier.classify batch --out work/taxonomy_labels.jsonl
  python -m kb_classifier.taxonomy_classifier.classify batch --limit 5000 --out labels.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..common.anchors import Anchor, embed_anchors, flatten_taxonomy
from ..common.corpus import Document, load_manifest, iter_documents, read_document, parse_document_text
from ..common.embedder import BgeM3Embedder
from ..common.matching import MatchResult, match_hierarchical
from ..config.settings import SETTINGS, Settings
from ..config.taxonomy_current import load_current_taxonomy

log = logging.getLogger("kb_taxonomy_classifier")

# ---------------------------------------------------------------------------
# FROZEN PRODUCTION TAXONOMY VERSION (task 9.1 "freeze version")
#
# The taxonomy classifier pins a specific Stage A round as its production
# taxonomy so it does NOT drift every time Stage A generates a new round.
# It resolves to config/taxonomy_v<PINNED_TAXONOMY_VERSION>[_<count>].py.
#
# To promote a newer Stage A round to production: bump this number (and record
# the change / bootstrap report it came from). Passing an explicit
# ``taxonomy_version`` (CLI --taxonomy-version) still overrides this pin.
# Set to None to fall back to "latest" (NOT recommended for production).
PINNED_TAXONOMY_VERSION: Optional[int] = 7
# ---------------------------------------------------------------------------

# Status values for a classified document.
STATUS_ASSIGNED = "ASSIGNED"   # full L1>L2>L3 path above all thresholds
STATUS_PARTIAL = "PARTIAL"     # matched some levels, fell below a lower one
STATUS_UNKNOWN = "UNKNOWN"     # L1 failed AND no L2/L3 deep-fallback evidence
STATUS_FALLBACK = "FALLBACK"   # L1 gate failed but a deep L2/L3 node cleared its own threshold


@dataclass
class LevelAssignment:
    key: str
    name: str
    score: float


@dataclass
class Classification:
    """The Stage B result for one document."""
    status: str
    levels: List[LevelAssignment] = field(default_factory=list)  # 0..3 entries
    # convenience mirrors (None when not assigned at that level)
    l1: Optional[LevelAssignment] = None
    l2: Optional[LevelAssignment] = None
    l3: Optional[LevelAssignment] = None
    depth: int = 0

    @property
    def path_keys(self) -> List[str]:
        return [lv.key for lv in self.levels]

    @property
    def path_names(self) -> List[str]:
        return [lv.name for lv in self.levels]

    @property
    def breadcrumb(self) -> str:
        return " > ".join(self.path_names)

    def to_okf_metadata(self, doc_id: Optional[str] = None) -> dict:
        """OKF-style classification metadata for one document.

        Shape is intentionally flat and JSON-friendly so it can ride along as
        document metadata into the OKF pipeline / vector store.
        """
        md: dict = {
            "classification_status": self.status,
            "classification_depth": self.depth,
            "category_path_keys": self.path_keys,
            "category_path_names": self.path_names,
            "category_breadcrumb": self.breadcrumb,
            "level_scores": {
                f"L{i+1}": round(lv.score, 6) for i, lv in enumerate(self.levels)
            },
            "l1_key": self.l1.key if self.l1 else None,
            "l2_key": self.l2.key if self.l2 else None,
            "l3_key": self.l3.key if self.l3 else None,
        }
        if doc_id is not None:
            md = {"doc_id": doc_id, **md}
        return md


class TaxonomyClassifier:
    """Loads a frozen taxonomy + thresholds and classifies documents.

    Construct once (loads the pinned taxonomy, embeds ~300 anchors, is ready),
    then call ``classify_documents`` / ``classify_text`` any number of times.
    Cheap enough to build once at startup and reuse for every imported document.

    By default the taxonomy is the pinned production version
    (``PINNED_TAXONOMY_VERSION``); pass ``taxonomy_version`` to override.
    """

    def __init__(
        self,
        cfg: Settings = SETTINGS,
        *,
        taxonomy_version: Optional[int] = None,
        thresholds_path: Optional[str] = None,
    ) -> None:
        self.cfg = cfg

        # --- taxonomy (frozen Stage A artifact) ---
        # Default to the pinned production version so classification does not
        # drift with Stage A; an explicit taxonomy_version still overrides it.
        resolved_version = (
            taxonomy_version if taxonomy_version is not None else PINNED_TAXONOMY_VERSION
        )
        self.taxonomy, self.taxonomy_source = load_current_taxonomy(version=resolved_version)
        self.anchors: List[Anchor] = flatten_taxonomy(self.taxonomy)
        self._anchor_by_key: Dict[str, Anchor] = {a.key: a for a in self.anchors}
        self._row_by_key: Dict[str, int] = {a.key: i for i, a in enumerate(self.anchors)}
        # Row indices of the L2 and L3 anchors, used only by the Deep Fallback
        # path (when the L1 gate fails). Precomputed once so fallback is a single
        # matmul against already-loaded anchor vectors -- no re-embedding.
        self._l2_rows: List[int] = [i for i, a in enumerate(self.anchors) if a.level == 2]
        self._l3_rows: List[int] = [i for i, a in enumerate(self.anchors) if a.level == 3]

        # --- thresholds (frozen Stage A artifact) ---
        self.thresholds_path = thresholds_path or cfg.paths.thresholds_out_path
        self.thresholds = self._load_thresholds(self.thresholds_path)

        # --- embedding + anchor vectors (anchor cache is shared with Stage A) ---
        self.embedder = BgeM3Embedder(cfg.embedding)
        self.anchor_vecs = embed_anchors(
            self.embedder, self.anchors, cfg.paths.anchor_cache_path,
            include_breadcrumb=cfg.matching.include_breadcrumb,
            embed_fingerprint=cfg.embedding_fingerprint(),
        )
        log.info("[taxonomy_classifier] ready: taxonomy=%s (%d anchors), thresholds L1=%.4f L2=%.4f L3=%.4f",
                 self.taxonomy_source, len(self.anchors),
                 self.thresholds["L1"], self.thresholds["L2"], self.thresholds["L3"])

    # ------------------------------------------------------------------
    @staticmethod
    def _load_thresholds(path: str) -> Dict[str, float]:
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"thresholds file not found: {path}. Run Stage A first to produce it."
            )
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        try:
            return {"L1": float(data["L1"]), "L2": float(data["L2"]), "L3": float(data["L3"])}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"malformed thresholds file {path}: {exc}") from exc

    # ------------------------------------------------------------------
    def _apply_thresholds(self, m: MatchResult) -> Classification:
        """Turn a raw hierarchical top-down match into a thresholded Classification.

        This is the ORIGINAL top-down behavior and is used unchanged whenever the
        L1 gate passes. When the L1 gate fails, the caller (classify_vectors)
        does NOT rely on this function's UNKNOWN result directly; it first tries
        the Deep Fallback path (see _deep_fallback).
        """
        t1, t2, t3 = self.thresholds["L1"], self.thresholds["L2"], self.thresholds["L3"]
        log.debug("[taxonomy_classifier] _apply_thresholds: L1=%.4f/%.4f L2=%.4f/%.4f "
                  "L3=%.4f/%.4f keys=(%s,%s,%s)",
                  m.l1_score, t1, m.l2_score, t2, m.l3_score, t3,
                  m.l1_key, m.l2_key, m.l3_key)

        # L1 gate.
        if not (m.l1_score >= t1):
            return Classification(status=STATUS_UNKNOWN, levels=[], depth=0)

        a1 = self._anchor_by_key.get(m.l1_key)
        lv1 = LevelAssignment(m.l1_key, a1.name if a1 else m.l1_key, m.l1_score)

        # L2 gate.
        if m.l2_key is None or not (m.l2_score >= t2):
            return Classification(status=STATUS_PARTIAL, levels=[lv1], l1=lv1, depth=1)

        a2 = self._anchor_by_key.get(m.l2_key)
        lv2 = LevelAssignment(m.l2_key, a2.name if a2 else m.l2_key, m.l2_score)

        # L3 gate.
        if m.l3_key is None or not (m.l3_score >= t3):
            return Classification(status=STATUS_PARTIAL, levels=[lv1, lv2],
                                  l1=lv1, l2=lv2, depth=2)

        a3 = self._anchor_by_key.get(m.l3_key)
        lv3 = LevelAssignment(m.l3_key, a3.name if a3 else m.l3_key, m.l3_score)
        return Classification(status=STATUS_ASSIGNED, levels=[lv1, lv2, lv3],
                              l1=lv1, l2=lv2, l3=lv3, depth=3)

    # ------------------------------------------------------------------
    def _deep_fallback(self, doc_vec: np.ndarray) -> Classification:
        """Deep Fallback, used ONLY when the L1 gate has already failed.

        Computes similarity of this single document vector against ALL anchors
        (one matmul against the already-loaded ``self.anchor_vecs`` -- no
        re-embedding of the document or the anchors). Among the L2 and L3
        anchors, keeps those whose raw cosine score clears their OWN level
        threshold (L2 uses L2 threshold, L3 uses L3 threshold), then selects the
        single candidate with the highest raw score. The chosen anchor's stored
        ancestor path (``Anchor.path_keys``) yields the full taxonomy path.

        Returns a FALLBACK Classification, or an UNKNOWN Classification if no L2
        or L3 anchor clears its threshold.
        """
        t2, t3 = self.thresholds["L2"], self.thresholds["L3"]
        sims = self.anchor_vecs @ doc_vec  # [n_anchors] cosine (all L2-normalised)

        # Gather (row, score) candidates that clear their own level threshold.
        best_row = -1
        best_score = -np.inf
        for row in self._l2_rows:
            s = float(sims[row])
            if s >= t2 and s > best_score:
                best_row, best_score = row, s
        for row in self._l3_rows:
            s = float(sims[row])
            if s >= t3 and s > best_score:
                best_row, best_score = row, s

        if best_row < 0:
            log.info("[taxonomy_classifier] deep fallback: no L2/L3 anchor cleared "
                     "its threshold (L2>=%.4f, L3>=%.4f) -> UNKNOWN", t2, t3)
            return Classification(status=STATUS_UNKNOWN, levels=[], depth=0)

        chosen = self.anchors[best_row]
        log.info("[taxonomy_classifier] deep fallback: selected L%d %s (score=%.4f) "
                 "-> path=%s", chosen.level, chosen.key, best_score, chosen.breadcrumb)

        # Build the full ancestor path from the chosen anchor's stored path_keys.
        # Each level records its own anchor's raw similarity (already in `sims`);
        # the chosen node's score is best_score by construction.
        levels: List[LevelAssignment] = []
        for k in chosen.path_keys:
            a = self._anchor_by_key.get(k)
            name = a.name if a else k
            row = self._row_by_key.get(k)
            score = float(sims[row]) if row is not None else 0.0
            levels.append(LevelAssignment(k, name, score))

        return Classification(
            status=STATUS_FALLBACK,
            levels=levels,
            l1=levels[0] if len(levels) >= 1 else None,
            l2=levels[1] if len(levels) >= 2 else None,
            l3=levels[2] if len(levels) >= 3 else None,
            depth=len(levels),
        )

    def classify_vectors(self, doc_vecs: np.ndarray) -> List[Classification]:
        """Classify a matrix of L2-normalised document vectors.

        Top-down + Deep Fallback:
          * Run the existing hierarchical top-down match (unchanged).
          * If the L1 gate passes, keep the top-down result exactly as before.
          * If the L1 gate fails, try the Deep Fallback on that document only.
        """
        log.info("[taxonomy_classifier] classify_vectors: matching %s against %d anchors",
                 getattr(doc_vecs, "shape", "?"), len(self.anchors))
        matches = match_hierarchical(doc_vecs, self.anchors, self.anchor_vecs)
        t1 = self.thresholds["L1"]

        results: List[Classification] = []
        for i, m in enumerate(matches):
            if m.l1_score >= t1:
                # L1 passed -> ORIGINAL top-down behavior, untouched.
                results.append(self._apply_thresholds(m))
            else:
                # L1 failed -> Deep Fallback on this single document vector.
                log.info("[taxonomy_classifier] L1 gate failed (best L1=%s score=%.4f < %.4f); "
                         "trying deep fallback", m.l1_key, m.l1_score, t1)
                results.append(self._deep_fallback(doc_vecs[i]))

        log.info("[taxonomy_classifier] classify_vectors: produced %d classification(s)",
                 len(results))
        return results

    def classify_documents(self, docs: Sequence[Document]) -> List[Classification]:
        """Embed and classify a batch of parsed documents."""
        log.info("[taxonomy_classifier] classify_documents: %d document(s)", len(docs))
        if not docs:
            return []
        vecs = self.embedder.encode_documents(docs)
        results = self.classify_vectors(vecs)
        for cl in results:
            log.info("[taxonomy_classifier] -> status=%s depth=%d path=%r",
                     cl.status, cl.depth, cl.breadcrumb)
        return results

    def classify_text(self, title: str, body: str) -> Classification:
        """Classify a single (title, body). Uses the same embed_text rendering
        (title-weighting + truncation) as Stage A so scores are comparable."""
        log.info("[taxonomy_classifier] classify_text: title=%r body_len=%d",
                 (title or "")[:80], len(body or ""))
        doc = Document(
            doc_index=0, doc_id="adhoc", rel_path="adhoc", stratum="adhoc",
            source="adhoc", title=title or "", body=body or "",
        )
        return self.classify_documents([doc])[0]


# Backwards-compatible alias (formerly the public name under stage_b).
Classifier = TaxonomyClassifier


# ---------------------------------------------------------------------------
# batch classification over the corpus manifest
# ---------------------------------------------------------------------------


def _iter_batches(seq: Sequence, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def classify_corpus(
    classifier: "TaxonomyClassifier",
    out_path: str,
    *,
    cfg: Settings = SETTINGS,
    limit: Optional[int] = None,
    batch_size: int = 512,
) -> Dict[str, int]:
    """Classify documents from the frozen manifest, writing one JSON line per doc.

    Reuses the frozen ``work/manifest.jsonl`` (so doc_ids line up with Stage A /
    the OKF pipeline). Documents are read and embedded in batches. Returns a
    small summary of status counts.
    """
    manifest_path = cfg.paths.manifest_path
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(
            f"no manifest at {manifest_path}. Build one with "
            "`python -m kb_classifier.run_embed manifest` first."
        )
    entries = load_manifest(manifest_path)
    if limit is not None:
        entries = entries[:limit]
    n = len(entries)
    log.info("[taxonomy_classifier] classifying %d document(s) from %s", n, manifest_path)

    counts = {STATUS_ASSIGNED: 0, STATUS_PARTIAL: 0, STATUS_FALLBACK: 0, STATUS_UNKNOWN: 0}
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    tmp = out_path + ".tmp"
    t0 = time.time()
    written = 0

    with open(tmp, "w", encoding="utf-8") as fh:
        for start in range(0, n, batch_size):
            batch_entries = entries[start:start + batch_size]
            docs = [read_document(cfg.corpus.root, e) for e in batch_entries]
            results = classifier.classify_documents(docs)
            for e, doc, cl in zip(batch_entries, docs, results):
                counts[cl.status] = counts.get(cl.status, 0) + 1
                md = cl.to_okf_metadata(doc_id=e.doc_id)
                md["rel_path"] = e.rel_path
                md["source"] = e.source
                md["title"] = doc.title
                fh.write(json.dumps(md, ensure_ascii=False) + "\n")
                written += 1
            log.info("[taxonomy_classifier]   classified %d/%d (%.0f docs/s)",
                     min(start + batch_size, n), n,
                     written / max(time.time() - t0, 1e-6))

    os.replace(tmp, out_path)
    total = sum(counts.values())
    log.info("[taxonomy_classifier] wrote %d labels -> %s", written, out_path)
    log.info("[taxonomy_classifier] status breakdown: ASSIGNED=%d (%.1f%%) PARTIAL=%d (%.1f%%) "
             "FALLBACK=%d (%.1f%%) UNKNOWN=%d (%.1f%%)",
             counts[STATUS_ASSIGNED], 100.0 * counts[STATUS_ASSIGNED] / max(total, 1),
             counts[STATUS_PARTIAL], 100.0 * counts[STATUS_PARTIAL] / max(total, 1),
             counts[STATUS_FALLBACK], 100.0 * counts[STATUS_FALLBACK] / max(total, 1),
             counts[STATUS_UNKNOWN], 100.0 * counts[STATUS_UNKNOWN] / max(total, 1))
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy in ("sentence_transformers", "transformers", "httpx", "httpcore",
                  "urllib3", "filelock", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _print_classification(cl: Classification) -> None:
    print(json.dumps(cl.to_okf_metadata(), ensure_ascii=False, indent=2))


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m kb_classifier.taxonomy_classifier.classify",
        description="Per-article taxonomy classifier (consumes frozen taxonomy + thresholds).",
    )
    p.add_argument("--taxonomy-version", type=int, default=None,
                   help=f"pin a specific taxonomy_v<N>.py; default = pinned production "
                        f"version (v{PINNED_TAXONOMY_VERSION})")
    p.add_argument("--thresholds", default=None,
                   help="path to thresholds.json; default = config/thresholds.json")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("text", help="classify one document given --title/--body")
    sp.add_argument("--title", default="")
    sp.add_argument("--body", default="")

    sp = sub.add_parser("file", help="classify one document from a .txt file")
    sp.add_argument("path")

    sp = sub.add_parser("batch", help="classify all manifest documents to a jsonl")
    sp.add_argument("--out", default=os.path.join(SETTINGS.paths.work_dir, "taxonomy_labels.jsonl"))
    sp.add_argument("--limit", type=int, default=None)
    sp.add_argument("--batch-size", type=int, default=512)

    args = p.parse_args(argv)
    _setup_logging()
    log.info("[taxonomy_classifier] command=%s taxonomy_version=%s thresholds=%s",
             args.command, args.taxonomy_version, args.thresholds)

    log.info("[taxonomy_classifier] constructing classifier ...")
    clf = TaxonomyClassifier(SETTINGS, taxonomy_version=args.taxonomy_version,
                             thresholds_path=args.thresholds)

    if args.command == "text":
        log.info("[taxonomy_classifier] classifying inline text ...")
        _print_classification(clf.classify_text(args.title, args.body))
        return 0

    if args.command == "file":
        log.info("[taxonomy_classifier] reading file: %s", args.path)
        with open(args.path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        title, body = parse_document_text(raw)
        log.info("[taxonomy_classifier] parsed file: title=%r body_len=%d",
                 title[:80], len(body))
        _print_classification(clf.classify_text(title, body))
        return 0

    if args.command == "batch":
        log.info("[taxonomy_classifier] batch mode: out=%s limit=%s batch_size=%d",
                 args.out, args.limit, args.batch_size)
        classify_corpus(clf, args.out, cfg=SETTINGS,
                        limit=args.limit, batch_size=args.batch_size)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
