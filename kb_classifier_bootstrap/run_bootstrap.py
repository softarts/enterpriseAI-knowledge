"""Main orchestrator for Stage A (Bootstrap).

Chains: load manifest -> load embedding cache -> build+embed anchors -> match
L1/L2/L3 -> fit thresholds -> gap discovery -> LLM naming -> emit taxonomy.py +
thresholds.json -> write bootstrap_report.md.

Embedding is NOT done here: it is the one expensive stage and lives in its own
resumable CLI (run_embed.py). This orchestrator assumes the embedding cache is
already COMPLETE (``--skip-embed`` is the default and only supported mode) and
fails clearly if it is not.

This is one round of the versioned discovery loop:

    corpus scope N (--limit)
      -> classify with the CURRENT taxonomy
      -> UNKNOWN
      -> HDBSCAN discovery
      -> LLM naming
      -> a COMPLETE new taxonomy  (taxonomy_v<N>.py, and taxonomy.py = latest)

Default mode only sends the round's UNKNOWN documents into discovery.
``--rediscover-all`` instead sends the ENTIRE scope into discovery (a heavier,
global re-discovery mode). See the README "Progressively Expanding Corpus and
Taxonomy Discovery" section.

Usage
-----
  python -m kb_classifier_bootstrap.run_bootstrap --limit 30000     # round on 30k
  python -m kb_classifier_bootstrap.run_bootstrap --limit 100000    # next round on 100k
  python -m kb_classifier_bootstrap.run_bootstrap --limit 100000 --rediscover-all
  python -m kb_classifier_bootstrap.run_bootstrap --dry-run         # no LLM calls
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Dict, List, Optional

import numpy as np

from .bootstrap import anchors as anchors_mod
from .bootstrap import discovery as discovery_mod
from .bootstrap import emit as emit_mod
from .bootstrap import matching as matching_mod
from .bootstrap import naming as naming_mod
from .bootstrap import report as report_mod
from .bootstrap import thresholds as thresholds_mod
from .bootstrap.corpus import load_manifest, iter_documents
from .bootstrap.embedder import BgeM3Embedder, existing_shard_starts, load_all_embeddings, plan_shards
from .config.settings import SETTINGS
from .config.taxonomy_current import load_current_taxonomy
from .config.taxonomy_seed import SEED_TAXONOMY, count_by_level, validate_taxonomy

log = logging.getLogger("kb_bootstrap")

_NOISY = ("sentence_transformers", "transformers", "httpx", "httpcore", "urllib3",
          "filelock", "huggingface_hub", "PIL", "matplotlib")


def setup_logging(log_path: Optional[str]) -> None:
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_path:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )
    for n in _NOISY:
        logging.getLogger(n).setLevel(logging.WARNING)


def _ensure_embeddings_complete(cfg, need_docs: Optional[int] = None) -> int:
    """Ensure at least ``need_docs`` (default: all) manifest rows are embedded.

    Returns the number of documents available for this round: the full manifest
    length when need_docs is None, otherwise min(need_docs, manifest length).
    Only the shards covering the first ``need_docs`` rows must be present, so a
    small --limit round does not require the whole corpus to be embedded.
    """
    entries = load_manifest(cfg.paths.manifest_path)
    n_manifest = len(entries)
    scope = n_manifest if need_docs is None else min(need_docs, n_manifest)

    shards = plan_shards(n_manifest, cfg.embedding.shard_size)
    # Only shards overlapping [0, scope) are required for this round.
    required = [s for s in shards if s.start < scope]
    have = existing_shard_starts(cfg.paths.embed_dir)
    missing = [s.start for s in required if s.start not in have]
    if missing:
        log.error("[run] embedding cache is INCOMPLETE for a scope of %d docs "
                  "(%d/%d required shards; first missing row %d). Run "
                  "`python -m kb_classifier_bootstrap.run_embed embed` first.",
                  scope, len(required) - len(missing), len(required), missing[0])
        raise SystemExit(2)
    return scope


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m kb_classifier_bootstrap.run_bootstrap",
        description="Stage A bootstrap orchestrator.",
    )
    p.add_argument("--skip-embed", action="store_true", default=True,
                   help="(default) assume embedding cache is complete")
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="corpus scope for this round: use at most the first N "
                        "documents of the manifest (default: the whole manifest)")
    p.add_argument("--rediscover-all", action="store_true",
                   help="send the ENTIRE scope into discovery instead of only the "
                        "UNKNOWN documents (heavier global re-discovery mode)")
    p.add_argument("--dry-run", action="store_true",
                   help="skip LLM naming (discovered nodes get placeholder names)")
    args = p.parse_args(argv)

    cfg = SETTINGS
    setup_logging(cfg.paths.run_log_path)

    # Shared version number for this round's taxonomy_v<N>.py, report and snapshot.
    version = cfg.paths.next_version()
    prev_version = cfg.paths.previous_version(version)

    log.info("=" * 78)
    log.info("STAGE A BOOTSTRAP - discovery round v%d%s",
             version, " [REDISCOVER-ALL]" if args.rediscover_all else "")
    log.info("=" * 78)
    for line in cfg.describe():
        log.info(line)

    validate_taxonomy(SEED_TAXONOMY)

    # ---- current taxonomy (what this round classifies against) ----
    current_tax, tax_source = load_current_taxonomy()
    validate_taxonomy(current_tax)
    base_counts = count_by_level(current_tax)
    log.info("[run] current taxonomy (%s): L1=%d L2=%d L3=%d",
             tax_source, base_counts[1], base_counts[2], base_counts[3])

    # ---- load manifest + embeddings for this round's scope ----
    n_docs = _ensure_embeddings_complete(cfg, need_docs=args.limit)
    entries = load_manifest(cfg.paths.manifest_path)
    n_manifest = len(entries)
    # Load only the shard-aligned prefix covering this round's scope, then slice
    # to exactly n_docs. This lets a small --limit round run without the whole
    # corpus being embedded. doc_index i == embedding row i == manifest position
    # i is guaranteed, so entries[:n_docs] and doc_vecs[:n_docs] stay aligned.
    shard_size = cfg.embedding.shard_size
    load_rows = min(
        n_manifest,
        ((n_docs + shard_size - 1) // shard_size) * shard_size,  # round up to shard
    )
    log.info("[run] loading embeddings (manifest=%d, scope=%d, loading %d shard-aligned rows) ...",
             n_manifest, n_docs, load_rows)
    doc_vecs = load_all_embeddings(cfg.paths.embed_dir, load_rows, shard_size)
    if n_docs < doc_vecs.shape[0]:
        doc_vecs = doc_vecs[:n_docs]
    if n_docs < n_manifest:
        entries = entries[:n_docs]
        log.info("[run] scope limited to first %d of %d manifest documents (--limit)",
                 n_docs, n_manifest)

    # ---- anchors (from the CURRENT taxonomy) ----
    log.info("[run] building + embedding anchors from the current taxonomy ...")
    anchor_list = anchors_mod.flatten_taxonomy(current_tax)
    embedder = BgeM3Embedder(cfg.embedding)
    anchor_vecs = anchors_mod.embed_anchors(
        embedder, anchor_list, cfg.paths.anchor_cache_path,
        include_breadcrumb=cfg.matching.include_breadcrumb,
        embed_fingerprint=cfg.embedding_fingerprint(),
    )

    # ---- matching ----
    log.info("[run] hierarchical matching ...")
    matches = matching_mod.match_hierarchical(doc_vecs, anchor_list, anchor_vecs)
    matching_mod.save_match_results(matches, anchor_list, cfg.paths.match_result_path)
    scores = matching_mod.level_scores(matches)

    # per-L1 distribution
    from collections import Counter
    l1_counter = Counter(m.l1_key for m in matches)
    l1_distribution = list(l1_counter.items())

    # ---- thresholds ----
    log.info("[run] fitting thresholds ...")
    threshold_results = [
        thresholds_mod.fit_threshold(scores["L1"], "L1", cfg.thresholds),
        thresholds_mod.fit_threshold(scores["L2"], "L2", cfg.thresholds),
        thresholds_mod.fit_threshold(scores["L3"], "L3", cfg.thresholds),
    ]
    thr = {r.level: r.value for r in threshold_results}
    log.info("[run] thresholds: L1=%.4f L2=%.4f L3=%.4f", thr["L1"], thr["L2"], thr["L3"])

    # fully assigned = cleared all three
    fully_assigned = sum(
        1 for m in matches
        if m.l1_score >= thr["L1"]
        and m.l2_key is not None and m.l2_score >= thr["L2"]
        and m.l3_key is not None and m.l3_score >= thr["L3"]
    )

    # ---- discovery ----
    if args.rediscover_all:
        # Global re-discovery: the ENTIRE scope goes into a single discovery
        # pool (no UNKNOWN filtering). Clusters become fresh top-level (L1)
        # categories via emit's discovered-L1 path.
        log.info("[run] gap discovery [REDISCOVER-ALL]: whole scope of %d docs "
                 "in a single pool", n_docs)
        pools = {(1, None): list(range(n_docs))}
    else:
        log.info("[run] gap discovery: UNKNOWN documents only")
        pools = discovery_mod.build_unassigned_pools(matches, thr)
    clusters, pool_reports = discovery_mod.discover(pools, doc_vecs, cfg.discovery,
                                                    seed=cfg.corpus.sampling_seed)

    # UNKNOWN counts per level = pool noise + not-clustered small pools
    unknown_by_level: Dict[int, int] = {1: 0, 2: 0, 3: 0}
    for pr in pool_reports:
        unknown_by_level[pr.level] = unknown_by_level.get(pr.level, 0) + pr.n_unknown

    # ---- naming ----
    # breadcrumb lookup for parents (so the prompt knows where the node sits)
    breadcrumb_of: Dict[Optional[str], str] = {a.key: a.breadcrumb for a in anchor_list}
    breadcrumb_of[None] = ""

    if args.dry_run:
        log.warning("[run] --dry-run: skipping LLM naming; discovered clusters get "
                    "placeholder names")
        names: Dict[int, naming_mod.NamingResult] = {}
        existing: set = set()
        for pos, c in enumerate(clusters):
            if c.unknown:
                continue
            nm = f"Discovered {c.parent_key or 'root'} Topic"
            key = naming_mod.snake_key(nm, existing)
            existing.add(key)
            names[pos] = naming_mod.NamingResult(
                name=nm, desc=f"Placeholder (dry-run) for a discovered cluster under "
                              f"{c.parent_key}.", model="(dry-run)", raw_response="",
                node_key=key, naming_failed=False)
    else:
        log.info("[run] naming %d discovered cluster(s) with %s ...",
                 sum(1 for c in clusters if not c.unknown), cfg.naming.primary_model)
        # load only the documents we actually need (representatives)
        docs = _load_documents(cfg, entries)
        names = naming_mod.name_clusters(
            clusters, docs, cfg.naming,
            cache_path=cfg.paths.naming_cache_path, breadcrumb_of=breadcrumb_of)

    # ---- emit ----
    # Each round regenerates a COMPLETE taxonomy = the CURRENT taxonomy (what
    # this round classified against) + THIS round's discovered nodes grafted
    # onto their parents. The graft base MUST be current_tax, not the seed:
    # discovery ran against current_tax, so a cluster's parent_key may be a
    # node that only exists in current_tax (a prior round's discovered node).
    # Grafting onto the bare seed would silently drop every cluster discovered
    # under such a parent ("parent not found"), which breaks the progressive
    # refinement loop -- a branch discovered in round N could never be deepened
    # in round N+1. Building on current_tax lets the taxonomy grow round over
    # round, matching the README's "生成一份完整的新 taxonomy" contract.
    seed_counts = count_by_level(SEED_TAXONOMY)
    log.info("[run] emitting taxonomy v%d (current taxonomy + this round's discoveries) ...",
             version)
    final_tax = emit_mod.build_final_taxonomy(current_tax, clusters, names)
    validate_taxonomy(final_tax)  # discovered grafts must keep the tree valid
    final_counts = count_by_level(final_tax)
    discovered_counts = {lvl: final_counts[lvl] - seed_counts[lvl] for lvl in (1, 2, 3)}

    meta = {
        "taxonomy_version": version,
        "n_documents": n_docs,
        "scope_limit": args.limit if args.limit is not None else "full-manifest",
        "rediscover_all": args.rediscover_all,
        "classified_against": tax_source,
        "embedding_model": cfg.embedding.model_name,
        "naming_model": cfg.naming.primary_model,
        "seed_nodes": sum(seed_counts.values()),
        "discovered_nodes": sum(discovered_counts.values()),
    }
    # Write the per-round versioned file AND update the latest pointer. Both are
    # importable modules with a TAXONOMY dict; taxonomy.py always mirrors the
    # newest taxonomy_v<N>.py. History (older taxonomy_v<N>.py) is never touched.
    # Sample-count label from THIS round's actual document count (never
    # hard-coded): taxonomy_v<N>_<count>.py, e.g. taxonomy_v4_100k.py.
    count_label = cfg.paths.sample_count_label(n_docs)
    meta["sample_count"] = count_label
    taxonomy_version_path = cfg.paths.taxonomy_version_path(version, count_label)
    emit_mod.write_taxonomy_py(final_tax, taxonomy_version_path, meta=meta)
    emit_mod.write_taxonomy_py(final_tax, cfg.paths.taxonomy_out_path, meta=meta)

    emit_mod.write_thresholds_json(
        threshold_results, cfg.paths.thresholds_out_path,
        n_documents=n_docs, embedding_model=cfg.embedding.model_name,
        max_seq_length=cfg.embedding.max_seq_length,
    )

    # ---- report ----
    discovered_nodes = []
    for pos, c in enumerate(clusters):
        if c.unknown or pos not in names:
            continue
        nr = names[pos]
        discovered_nodes.append((c.level, c.parent_key, nr.name, c.size, nr.naming_failed))

    stats = report_mod.BootstrapStats(
        n_documents=n_docs,
        embedding_model=cfg.embedding.model_name,
        max_seq_length=cfg.embedding.max_seq_length,
        naming_model=cfg.naming.primary_model,
        seed_counts=seed_counts,
        discovered_counts=discovered_counts,
        thresholds=threshold_results,
        discovered_nodes=discovered_nodes,
        l1_distribution=l1_distribution,
        unknown_by_level=unknown_by_level,
        pool_reports=pool_reports,
        fully_assigned=fully_assigned,
        focus_l1_subtree=report_mod.focus_l1_subtree_counts(final_tax),
    )

    # Load the PREVIOUS round's snapshot (highest version below this one, found
    # dynamically) so the report can render a prev -> current diff.
    prev_snapshot = None
    if prev_version > 0:
        # The previous round's document count (hence its snapshot's count label)
        # is not known here, so locate it by version number regardless of suffix.
        prev_snapshot_path = cfg.paths.find_snapshot_for_version(prev_version)
        if prev_snapshot_path and os.path.exists(prev_snapshot_path):
            try:
                import json
                with open(prev_snapshot_path, "r", encoding="utf-8") as f:
                    prev_snapshot = json.load(f)
                log.info("[run] loaded prior snapshot for v%d->v%d comparison: %s",
                         prev_version, version, prev_snapshot_path)
            except (OSError, ValueError) as exc:
                log.warning("[run] could not load prior snapshot (%s); skipping comparison",
                            exc)

    # Versioned outputs all share the same N and the same sample-count label.
    # History is never overwritten.
    snapshot_out = cfg.paths.snapshot_path(version, count_label)
    report_path = cfg.paths.report_path_for_version(version, count_label)
    report_mod.write_report(report_path, stats,
                            v1_snapshot=prev_snapshot, snapshot_path=snapshot_out)

    log.info("=" * 78)
    log.info("DISCOVERY ROUND v%d COMPLETE", version)
    log.info("  taxonomy (versioned) -> %s", taxonomy_version_path)
    log.info("  taxonomy (latest)    -> %s", cfg.paths.taxonomy_out_path)
    log.info("  thresholds           -> %s", cfg.paths.thresholds_out_path)
    log.info("  report               -> %s", report_path)
    log.info("  snapshot             -> %s", snapshot_out)
    log.info("  classified against   : %s", tax_source)
    log.info("  mode                 : %s",
             "rediscover-all" if args.rediscover_all else "UNKNOWN-only")
    log.info("  seed nodes=%d  discovered nodes=%d  (L1/L2/L3 = %d/%d/%d)",
             sum(seed_counts.values()), sum(discovered_counts.values()),
             final_counts[1], final_counts[2], final_counts[3])
    log.info("=" * 78)
    return 0


def _load_documents(cfg, entries):
    """Read all documents once so naming can index representatives by doc_index."""
    log.info("[run] reading %d document bodies for naming representatives ...", len(entries))
    return list(iter_documents(cfg.corpus.root, entries, 0, len(entries)))


if __name__ == "__main__":
    sys.exit(main())
