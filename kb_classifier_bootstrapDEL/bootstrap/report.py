"""Generate bootstrap_report.md.

Covers the five items the brief requires:
  1. total documents in the bootstrap batch;
  2. node counts per level, split into seed-retained vs discovered-added;
  3. each discovered node's name + its cluster's document count;
  4. the qwen2.5-coder:7b vs qwen2.5:3b naming comparison (recorded N/A here:
     single local model qwen3-8b-mlx via LM Studio);
  5. per-level UNKNOWN counts and percentages.

Plus, per 01_STATUS.md 3.2, the corpus/taxonomy mismatch conclusion and the
per-L1 document distribution, so a reader sees immediately that the banking
skeleton barely matched and why.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .discovery import DiscoveredCluster, PoolReport
from .naming import NamingResult
from .thresholds import ThresholdResult

log = logging.getLogger(__name__)


@dataclass
class BootstrapStats:
    n_documents: int
    embedding_model: str
    max_seq_length: int
    naming_model: str

    # node counts
    seed_counts: Dict[int, int]                 # {1,2,3 -> n}
    discovered_counts: Dict[int, int]

    thresholds: List[ThresholdResult]

    # discovered clusters that became nodes: (level, parent_key, name, size, failed)
    discovered_nodes: List[Tuple[int, Optional[str], str, int, bool]]

    # per-L1 assigned distribution: l1_key -> count (documents whose L1 matched)
    l1_distribution: List[Tuple[str, int]]

    # UNKNOWN counts per level
    unknown_by_level: Dict[int, int]

    pool_reports: List[PoolReport]

    fully_assigned: int = 0                     # cleared all three levels

    # Per-focus-L1 L2/L3 subtree sizes in the FINAL taxonomy (seed+discovered),
    # for the three "heavy" L1s the brief calls out. Shape: {l1_key: (n_l2,n_l3)}.
    focus_l1_subtree: Dict[str, Tuple[int, int]] = None  # type: ignore

    # Naming-model comparison experiment (brief item #4). Not run on this
    # machine: a single local model (qwen3-8b-mlx via LM Studio) is configured,
    # so the qwen2.5-coder:7b vs qwen2.5:3b comparison is recorded as N/A.
    comparison_ran: bool = False
    comparison_rows: List[dict] = None  # type: ignore


# L1 keys the brief asks us to track growth under.
FOCUS_L1 = ("technology_engineering", "product_management", "risk_compliance")


def _pct(n: int, total: int) -> str:
    return f"{(100.0 * n / total):.2f}%" if total else "0.00%"


def focus_l1_subtree_counts(tax: Dict[str, dict]) -> Dict[str, Tuple[int, int]]:
    """(n_L2, n_L3) under each focus L1 in a taxonomy dict."""
    out: Dict[str, Tuple[int, int]] = {}
    for k in FOCUS_L1:
        spec = tax.get(k)
        if not spec:
            continue
        l2 = spec.get("children", {})
        n_l2 = len(l2)
        n_l3 = sum(len(v.get("children", {})) for v in l2.values())
        out[k] = (n_l2, n_l3)
    return out


def build_snapshot(stats: "BootstrapStats") -> dict:
    """Machine-readable summary of a run, saved beside the report for later diffs."""
    total = stats.n_documents
    unknown = {str(l): stats.unknown_by_level.get(l, 0) for l in (1, 2, 3)}
    return {
        "n_documents": total,
        "node_counts": {
            "L1": {"seed": stats.seed_counts.get(1, 0), "discovered": stats.discovered_counts.get(1, 0)},
            "L2": {"seed": stats.seed_counts.get(2, 0), "discovered": stats.discovered_counts.get(2, 0)},
            "L3": {"seed": stats.seed_counts.get(3, 0), "discovered": stats.discovered_counts.get(3, 0)},
        },
        "focus_l1_subtree": {k: list(v) for k, v in (stats.focus_l1_subtree or {}).items()},
        "discovered_nodes": [
            {"level": lvl, "parent": parent, "name": name, "size": size, "failed": failed}
            for (lvl, parent, name, size, failed) in stats.discovered_nodes
        ],
        "thresholds": {r.level: round(r.value, 6) for r in stats.thresholds},
        "threshold_methods": {r.level: r.method for r in stats.thresholds},
        "unknown_by_level": unknown,
        "unknown_total": sum(unknown.values()),
        "fully_assigned": stats.fully_assigned,
    }


def _fmt_delta(old, new) -> str:
    try:
        d = new - old
        sign = "+" if d > 0 else ""
        return f"{sign}{d}"
    except TypeError:
        return "-"


def _render_comparison(w, v1: dict, v2: dict) -> None:
    """Render the v1 -> v2 comparison section from two snapshots."""
    w("## v1 -> v2 comparison")
    w("")
    w(f"- Documents: v1 **{v1.get('n_documents')}** -> v2 **{v2.get('n_documents')}**")
    w("")

    # node counts per level
    w("### Node counts per level (seed + discovered = total)")
    w("")
    w("| Level | v1 total | v2 total | delta | v1 discovered | v2 discovered |")
    w("|---|---:|---:|---:|---:|---:|")
    for lvl in ("L1", "L2", "L3"):
        v1c = v1["node_counts"][lvl]; v2c = v2["node_counts"][lvl]
        v1t = v1c["seed"] + v1c["discovered"]; v2t = v2c["seed"] + v2c["discovered"]
        w(f"| {lvl} | {v1t} | {v2t} | {_fmt_delta(v1t, v2t)} | "
          f"{v1c['discovered']} | {v2c['discovered']} |")
    w("")

    # focus L1 subtree growth
    w("### L2/L3 growth under the heavy L1s")
    w("")
    w("Sub-node counts (L2, L3) under the three L1s the brief flags as data-heavy. "
      "Growth here means gap discovery found new sub-categories the seed skeleton "
      "missed.")
    w("")
    w("| L1 | v1 (L2, L3) | v2 (L2, L3) |")
    w("|---|---|---|")
    for k in FOCUS_L1:
        a = v1.get("focus_l1_subtree", {}).get(k)
        b = v2.get("focus_l1_subtree", {}).get(k)
        av = f"({a[0]}, {a[1]})" if a else "-"
        bv = f"({b[0]}, {b[1]})" if b else "-"
        w(f"| `{k}` | {av} | {bv} |")
    w("")

    # discovered clusters
    v1d = v1.get("discovered_nodes", [])
    v2d = v2.get("discovered_nodes", [])
    w("### Discovered clusters")
    w("")
    w(f"- Count: v1 **{len(v1d)}** -> v2 **{len(v2d)}**")
    w("")
    w("v1 discovered themes:")
    for n in v1d:
        w(f"  - L{n['level']} under `{n['parent']}`: {n['name']} ({n['size']} docs)")
    if not v1d:
        w("  - (none)")
    w("")
    w("v2 discovered themes:")
    for n in v2d:
        w(f"  - L{n['level']} under `{n['parent']}`: {n['name']} ({n['size']} docs)")
    if not v2d:
        w("  - (none)")
    w("")

    # thresholds
    w("### Threshold values")
    w("")
    w("| Level | v1 | v2 | v1 method | v2 method |")
    w("|---|---:|---:|---|---|")
    for lvl in ("L1", "L2", "L3"):
        w(f"| {lvl} | {v1['thresholds'].get(lvl)} | {v2['thresholds'].get(lvl)} | "
          f"{v1.get('threshold_methods', {}).get(lvl, '-')} | "
          f"{v2.get('threshold_methods', {}).get(lvl, '-')} |")
    w("")

    # UNKNOWN shares
    w("### UNKNOWN share by level")
    w("")
    w("| Level | v1 UNKNOWN | v1 share | v2 UNKNOWN | v2 share |")
    w("|---|---:|---:|---:|---:|")
    n1 = v1.get("n_documents", 0); n2 = v2.get("n_documents", 0)
    for lvl in ("1", "2", "3"):
        u1 = v1["unknown_by_level"].get(lvl, 0); u2 = v2["unknown_by_level"].get(lvl, 0)
        w(f"| L{lvl} | {u1} | {_pct(u1, n1)} | {u2} | {_pct(u2, n2)} |")
    ut1 = v1.get("unknown_total", 0); ut2 = v2.get("unknown_total", 0)
    w(f"| **total** | **{ut1}** | **{_pct(ut1, n1)}** | **{ut2}** | **{_pct(ut2, n2)}** |")
    w("")
    fa1 = v1.get("fully_assigned", 0); fa2 = v2.get("fully_assigned", 0)
    w(f"- Fully assigned (all three levels): v1 **{fa1}** ({_pct(fa1, n1)}) -> "
      f"v2 **{fa2}** ({_pct(fa2, n2)})")
    w("")


def write_report(path: str, stats: BootstrapStats,
                 v1_snapshot: Optional[dict] = None,
                 snapshot_path: Optional[str] = None) -> None:
    import json
    L: List[str] = []
    w = L.append

    w("# Bootstrap Report - KB Article Classifier (Stage A)")
    w("")
    w(f"- Generated for **{stats.n_documents}** bootstrap documents.")
    w(f"- Embedding model: `{stats.embedding_model}` (max_seq_length="
      f"{stats.max_seq_length}).")
    w(f"- Cluster-naming model: `{stats.naming_model}` (local, LM Studio "
      "OpenAI-compatible API).")
    w("")

    # ---- v1 -> v2 comparison (only when a prior snapshot is supplied) ----
    v2_snapshot = build_snapshot(stats)
    if v1_snapshot is not None:
        _render_comparison(w, v1_snapshot, v2_snapshot)

    # ---- Corpus / taxonomy mismatch (surfaced first, it frames everything) ----
    w("## Important: corpus vs taxonomy mismatch")
    w("")
    w("The hand-written taxonomy is a **banking** skeleton (per the original "
      "task). The bootstrap corpus, however, is the internal knowledge base of "
      "an **AI-inference platform company** (GPU clusters, model serving, "
      "quantization, evals, SLOs, Kubernetes, on-call, SDKs). The two do not "
      "align.")
    w("")
    w("Consequently the nine banking business-line L1s attract almost no "
      "documents; the overwhelming majority land under `Technology & "
      "Engineering` (which is why that branch was expanded to a detailed set of "
      "L2/L3 nodes). This is a known, expected data/requirement mismatch, not a "
      "defect. The per-L1 distribution below makes it explicit.")
    w("")

    # ---- 1 + per-L1 distribution ----
    w("## 1. Documents processed & per-L1 distribution")
    w("")
    w(f"Total bootstrap documents: **{stats.n_documents}**")
    w(f"Fully assigned to a complete L1>L2>L3 path: **{stats.fully_assigned}** "
      f"({_pct(stats.fully_assigned, stats.n_documents)})")
    w("")
    w("Documents by best-matched L1 (before thresholding):")
    w("")
    w("| L1 category | documents | share |")
    w("|---|---:|---:|")
    for l1_key, cnt in sorted(stats.l1_distribution, key=lambda kv: -kv[1]):
        w(f"| `{l1_key}` | {cnt} | {_pct(cnt, stats.n_documents)} |")
    w("")

    # ---- 2 node counts ----
    w("## 2. Taxonomy node counts (seed vs discovered)")
    w("")
    w("| Level | seed (retained) | discovered (added) | total |")
    w("|---|---:|---:|---:|")
    for lvl in (1, 2, 3):
        s = stats.seed_counts.get(lvl, 0)
        d = stats.discovered_counts.get(lvl, 0)
        w(f"| L{lvl} | {s} | {d} | {s + d} |")
    tot_s = sum(stats.seed_counts.values())
    tot_d = sum(stats.discovered_counts.values())
    w(f"| **all** | **{tot_s}** | **{tot_d}** | **{tot_s + tot_d}** |")
    w("")

    # ---- 3 discovered nodes ----
    w("## 3. Discovered nodes")
    w("")
    if stats.discovered_nodes:
        w("| Level | parent | discovered name | cluster docs | naming |")
        w("|---|---|---|---:|---|")
        for lvl, parent, name, size, failed in stats.discovered_nodes:
            tag = "fallback (naming_failed)" if failed else "LLM-named"
            w(f"| L{lvl} | `{parent}` | {name} | {size} | {tag} |")
    else:
        w("No new nodes were discovered: every unassigned pool was either below "
          "the minimum pool size or produced no HDBSCAN cluster above the minimum "
          "cluster size. See the pool diagnostics below.")
    w("")

    # ---- pool diagnostics ----
    w("### Gap-discovery pool diagnostics")
    w("")
    w("| Level | parent | pool size | clustered | min_cluster_size | clusters | noise/UNKNOWN |")
    w("|---|---|---:|---|---:|---:|---:|")
    for pr in sorted(stats.pool_reports, key=lambda r: (r.level, r.parent_key or "")):
        w(f"| L{pr.level} | `{pr.parent_key}` | {pr.pool_size} | "
          f"{'yes' if pr.clustered else 'no'} | "
          f"{pr.min_cluster_size if pr.min_cluster_size is not None else '-'} | "
          f"{pr.n_clusters} | {pr.n_unknown} |")
    w("")

    # ---- 4 naming model comparison (brief item #4) ----
    w("## 4. Naming model comparison (qwen2.5-coder:7b vs qwen2.5:3b)")
    w("")
    if stats.comparison_ran and stats.comparison_rows:
        w("| cluster | model | name | desc |")
        w("|---|---|---|---|")
        for row in stats.comparison_rows:
            w(f"| {row.get('cluster')} | `{row.get('model')}` | "
              f"{row.get('name')} | {row.get('desc')} |")
    else:
        w("**N/A - comparison not run.** The original task specified an Ollama "
          "setup with `qwen2.5-coder:7b` and `qwen2.5:3b`. This machine instead "
          "runs a single local model (`qwen3-8b-mlx`) served by LM Studio over an "
          "OpenAI-compatible API. With only one local generation model available, "
          "the two-model selection experiment is not applicable; all cluster "
          "naming used `qwen3-8b-mlx`. No second model's output was fabricated.")
    w("")

    # ---- 5 UNKNOWN ----
    w("## 5. Unclassified (UNKNOWN) documents by level")
    w("")
    w("Documents whose best match fell below the level threshold and which were "
      "not absorbed into any discovered cluster (pool too small, or HDBSCAN "
      "noise).")
    w("")
    w("| Level | UNKNOWN documents | share of corpus |")
    w("|---|---:|---:|")
    total_unknown = 0
    for lvl in (1, 2, 3):
        u = stats.unknown_by_level.get(lvl, 0)
        total_unknown += u
        w(f"| L{lvl} | {u} | {_pct(u, stats.n_documents)} |")
    w(f"| **total** | **{total_unknown}** | **{_pct(total_unknown, stats.n_documents)}** |")
    w("")

    # ---- thresholds ----
    w("## Threshold decisions")
    w("")
    w("| Level | threshold | method | samples | separation | reason |")
    w("|---|---:|---|---:|---:|---|")
    for r in stats.thresholds:
        sep = f"{r.separation:.3f}" if r.separation is not None else "-"
        w(f"| {r.level} | {r.value:.4f} | {r.method} | {r.n_samples} | {sep} | "
          f"{r.reason} |")
    w("")
    w("_Method `gmm` = midpoint of a two-component Gaussian mixture on the "
      "per-level best-score distribution. `p30_fallback` = 30th percentile, used "
      "when the two components were not separated enough or one was negligibly "
      "weighted (see reason). All thresholds clamped to a sane cosine range._")
    w("")

    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    os.replace(tmp, path)
    log.info("[report] wrote report -> %s", path)

    # Machine-readable snapshot for the next run's v1 -> v2 comparison.
    if snapshot_path:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(v2_snapshot, f, indent=2)
        log.info("[report] wrote snapshot -> %s", snapshot_path)
