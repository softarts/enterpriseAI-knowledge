"""Gap discovery: cluster the documents that don't fit the seed skeleton.

This is the ONLY place clustering is used (brief, step 3). Documents whose
best-match score at a level falls below that level's threshold are "unassigned"
at that level. They are pooled *per parent* -- a document that matched L1=Payments
but no L2 above threshold goes into the Payments L2 pool, and only competes with
other Payments-orphans, never with unassigned documents from another L1. This
keeps discovered nodes attached to the right branch.

For each pool:
  * pools smaller than min_pool_size are left as UNKNOWN (not clustered) -- a
    handful of documents is noise, and naming it would litter the taxonomy;
  * otherwise run sklearn.cluster.HDBSCAN with a min_cluster_size scaled to the
    pool (so a big pool isn't shattered into hundreds of tiny nodes);
  * very large pools are subsampled for the clustering step and the remainder
    assigned to the nearest discovered centroid (HDBSCAN is memory-hungry);
  * keep at most max_new_nodes_per_parent clusters (largest first);
  * for each kept cluster, pick the representatives_per_cluster documents closest
    to the centroid to feed the naming model.

Vectors are L2-normalised, so euclidean distance is monotone in cosine distance
and HDBSCAN's fast euclidean path is valid.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..config.settings import DiscoverySettings
from ..common.matching import MatchResult

log = logging.getLogger(__name__)

# Pool key: (level, parent_key). parent_key is None only for the L1 pool
# (documents that didn't match any L1 above the L1 threshold).
PoolKey = Tuple[int, Optional[str]]


@dataclass
class DiscoveredCluster:
    parent_key: Optional[str]
    level: int
    doc_indices: np.ndarray             # global document indices in this cluster
    centroid: np.ndarray
    representative_doc_indices: List[int]
    size: int
    unknown: bool = False               # True for the leftover UNKNOWN bucket
    label: Optional[str] = None         # HDBSCAN local label (diagnostics)


@dataclass
class PoolReport:
    """Per-pool diagnostics for the report / logs."""
    level: int
    parent_key: Optional[str]
    pool_size: int
    clustered: bool
    min_cluster_size: Optional[int]
    n_clusters: int
    n_noise: int
    n_unknown: int
    reason: str = ""


def build_unassigned_pools(
    matches: List[MatchResult],
    thresholds: Dict[str, float],
) -> Dict[PoolKey, List[int]]:
    """Group document indices into per-parent pools by first failing level.

    A document is placed in exactly one pool: the highest level at which it
    falls below threshold. If it clears L1 but fails L2, it lands in the L2 pool
    under its L1; if it clears L1 and L2 but fails L3, it lands in the L3 pool
    under its L2. Documents that clear all three levels are fully assigned and
    do not enter any pool.
    """
    t1 = thresholds["L1"]
    t2 = thresholds["L2"]
    t3 = thresholds["L3"]
    pools: Dict[PoolKey, List[int]] = {}

    for i, m in enumerate(matches):
        if not (m.l1_score >= t1):
            pools.setdefault((1, None), []).append(i)
        elif m.l2_key is None or not (m.l2_score >= t2):
            pools.setdefault((2, m.l1_key), []).append(i)
        elif m.l3_key is None or not (m.l3_score >= t3):
            pools.setdefault((3, m.l2_key), []).append(i)
        # else: fully assigned L1->L2->L3, no pool.

    log.info("[discover] built %d unassigned pool(s); sizes: %s",
             len(pools),
             ", ".join(f"(L{k[0]},{k[1]})={len(v)}"
                       for k, v in sorted(pools.items(), key=lambda kv: -len(kv[1]))[:10]))
    return pools


def choose_min_cluster_size(pool_size: int, cfg: DiscoverySettings) -> int:
    """Scale HDBSCAN min_cluster_size with the (effective) pool size.

    Formula: max(base, min(fraction * effective, cap)), with the tuned
    constants in DiscoverySettings (base=15, fraction=0.003, cap=50). See the
    settings comment for the empirical mcs sweep that motivated them: the old
    1%-of-pool rule pushed large pools past the point where HDBSCAN(eom) can
    form any cluster at all.

    ``effective`` is the pool size HDBSCAN actually sees: pools larger than
    ``max_pool_for_clustering`` are sub-sampled first (see _cluster_one_pool),
    so scaling min_cluster_size off the raw pool size would compute a threshold
    for a sample HDBSCAN never receives. Capping here keeps the fraction
    honest at full-corpus scale.
    """
    effective = min(pool_size, cfg.max_pool_for_clustering)
    scaled = int(cfg.min_cluster_size_pool_fraction * effective)
    return max(cfg.base_min_cluster_size, min(scaled, cfg.max_min_cluster_size))


def _representatives(
    centroid: np.ndarray,
    member_global_idx: np.ndarray,
    doc_vecs: np.ndarray,
    k: int,
) -> List[int]:
    """The k member documents whose vectors are closest to the centroid."""
    member_vecs = doc_vecs[member_global_idx]
    # cosine similarity to centroid (centroid not necessarily unit; normalise)
    c = centroid / max(float(np.linalg.norm(centroid)), 1e-12)
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        sims = member_vecs @ c
    sims = np.nan_to_num(sims, nan=-np.inf, posinf=-np.inf, neginf=-np.inf)
    top = np.argsort(-sims)[:k]
    return [int(member_global_idx[t]) for t in top]


def _cluster_one_pool(
    key: PoolKey,
    pool_idx: List[int],
    doc_vecs: np.ndarray,
    cfg: DiscoverySettings,
    rng: np.random.Generator,
) -> Tuple[List[DiscoveredCluster], PoolReport]:
    level, parent_key = key
    pool_size = len(pool_idx)
    pool_idx_arr = np.asarray(pool_idx, dtype=np.int64)

    if pool_size < cfg.min_pool_size:
        reason = f"pool size {pool_size} < min_pool_size {cfg.min_pool_size}: UNKNOWN"
        log.info("[discover] (L%d,%s) %s", level, parent_key, reason)
        unknown = DiscoveredCluster(
            parent_key=parent_key, level=level, doc_indices=pool_idx_arr,
            centroid=doc_vecs[pool_idx_arr].mean(axis=0) if pool_size else np.zeros(doc_vecs.shape[1]),
            representative_doc_indices=list(map(int, pool_idx_arr[:cfg.representatives_per_cluster])),
            size=pool_size, unknown=True,
        )
        return [unknown], PoolReport(level, parent_key, pool_size, False, None, 0, 0, pool_size, reason)

    # Subsample very large pools for the actual clustering step.
    if pool_size > cfg.max_pool_for_clustering:
        sample_local = rng.choice(pool_size, size=cfg.max_pool_for_clustering, replace=False)
        sample_local.sort()
        log.info("[discover] (L%d,%s) pool %d > %d: clustering on a %d-doc subsample",
                 level, parent_key, pool_size, cfg.max_pool_for_clustering,
                 cfg.max_pool_for_clustering)
    else:
        sample_local = np.arange(pool_size)

    sample_global = pool_idx_arr[sample_local]
    sample_vecs = doc_vecs[sample_global]

    mcs = choose_min_cluster_size(pool_size, cfg)

    # A pool that HDBSCAN sees with fewer samples than min_cluster_size cannot
    # form even one valid cluster (and sklearn's HDBSCAN raises if min_samples >
    # n_samples). Such a pool is between min_pool_size and the mcs floor: too
    # small to cluster, so it stays UNKNOWN rather than being forced into a node.
    if sample_vecs.shape[0] < mcs:
        reason = (f"pool size {pool_size} < min_cluster_size {mcs}: too small to "
                  f"form a cluster, UNKNOWN")
        log.info("[discover] (L%d,%s) %s", level, parent_key, reason)
        unknown = DiscoveredCluster(
            parent_key=parent_key, level=level, doc_indices=pool_idx_arr,
            centroid=doc_vecs[pool_idx_arr].mean(axis=0),
            representative_doc_indices=list(map(int, pool_idx_arr[:cfg.representatives_per_cluster])),
            size=pool_size, unknown=True,
        )
        return [unknown], PoolReport(level, parent_key, pool_size, False, mcs, 0, 0,
                                     pool_size, reason)

    log.info("[discover] (L%d,%s) clustering %d docs with HDBSCAN(min_cluster_size=%d, metric=%s)",
             level, parent_key, sample_vecs.shape[0], mcs, cfg.metric)

    from sklearn.cluster import HDBSCAN

    clusterer = HDBSCAN(
        min_cluster_size=mcs,
        metric=cfg.metric,
        cluster_selection_method=cfg.cluster_selection_method,
    )
    labels = clusterer.fit_predict(sample_vecs)

    unique = [lbl for lbl in np.unique(labels) if lbl != -1]
    n_noise = int(np.sum(labels == -1))
    log.info("[discover] (L%d,%s) HDBSCAN -> %d cluster(s), %d noise point(s)",
             level, parent_key, len(unique), n_noise)

    # Rank clusters by size, keep the largest max_new_nodes_per_parent.
    sized = []
    for lbl in unique:
        local_members = np.nonzero(labels == lbl)[0]
        sized.append((len(local_members), lbl, local_members))
    sized.sort(reverse=True)
    kept = sized[: cfg.max_new_nodes_per_parent]
    if len(sized) > cfg.max_new_nodes_per_parent:
        log.info("[discover] (L%d,%s) keeping top %d of %d clusters by size",
                 level, parent_key, cfg.max_new_nodes_per_parent, len(sized))

    # Compute centroids for kept clusters (from the sampled members).
    kept_centroids = []
    for _size, lbl, local_members in kept:
        global_members = sample_global[local_members]
        centroid = doc_vecs[global_members].mean(axis=0)
        kept_centroids.append((lbl, centroid, global_members))

    # If we subsampled, assign the remaining pool docs to the nearest kept
    # centroid so cluster sizes reflect the whole pool.
    clusters: List[DiscoveredCluster] = []
    if kept_centroids:
        cmat = np.stack([c / max(float(np.linalg.norm(c)), 1e-12) for _, c, _ in kept_centroids])
        assigned_members: Dict[int, List[int]] = {lbl: list(gm) for lbl, _, gm in kept_centroids}

        if pool_size > cfg.max_pool_for_clustering:
            leftover_local = np.setdiff1d(np.arange(pool_size), sample_local, assume_unique=False)
            leftover_global = pool_idx_arr[leftover_local]
            with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
                sims = doc_vecs[leftover_global] @ cmat.T      # [m, k]
            sims = np.nan_to_num(sims, nan=-np.inf, posinf=-np.inf, neginf=-np.inf)
            nearest = np.argmax(sims, axis=1)
            for pos, g in zip(nearest, leftover_global):
                lbl = kept_centroids[pos][0]
                assigned_members[lbl].append(int(g))

        for lbl, centroid, _gm in kept_centroids:
            members = np.asarray(sorted(assigned_members[lbl]), dtype=np.int64)
            reps = _representatives(centroid, members, doc_vecs, cfg.representatives_per_cluster)
            clusters.append(DiscoveredCluster(
                parent_key=parent_key, level=level, doc_indices=members,
                centroid=centroid, representative_doc_indices=reps,
                size=int(members.size), unknown=False, label=int(lbl),
            ))

    n_unknown = n_noise
    report = PoolReport(
        level=level, parent_key=parent_key, pool_size=pool_size,
        clustered=True, min_cluster_size=mcs, n_clusters=len(clusters),
        n_noise=n_noise, n_unknown=n_unknown,
        reason=f"HDBSCAN kept {len(clusters)} cluster(s)",
    )
    return clusters, report


def discover(
    pools: Dict[PoolKey, List[int]],
    doc_vecs: np.ndarray,
    cfg: DiscoverySettings,
    *,
    seed: int = 20260829,
) -> Tuple[List[DiscoveredCluster], List[PoolReport]]:
    """Run gap discovery over every pool. Returns (clusters, per-pool reports).

    Clusters with ``unknown=True`` represent the UNKNOWN bucket for a pool (not a
    new taxonomy node); the emitter and report treat them separately.
    """
    rng = np.random.default_rng(seed)
    all_clusters: List[DiscoveredCluster] = []
    reports: List[PoolReport] = []

    for key in sorted(pools, key=lambda k: (k[0], k[1] or "")):
        clusters, report = _cluster_one_pool(key, pools[key], doc_vecs, cfg, rng)
        all_clusters.extend(clusters)
        reports.append(report)

    n_real = sum(1 for c in all_clusters if not c.unknown)
    log.info("[discover] discovery complete: %d new cluster(s) across %d pool(s)",
             n_real, len(pools))
    return all_clusters, reports
