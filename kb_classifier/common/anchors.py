"""Flatten the taxonomy into anchors and embed them (with a cache).

An ``Anchor`` is one taxonomy node lifted out of the tree into a flat record the
matcher can score against. The text that actually gets embedded is
``"<breadcrumb>: <desc>"`` -- the parent breadcrumb disambiguates sibling nodes
that share vocabulary (e.g. ``Treasury > Cash Management`` vs
``Corporate Banking > Cash Management Services``), which a desc-only anchor
handles poorly.

Anchors are tiny (~300 nodes), so embedding them is a sub-second job. The npz
cache exists only so that the many downstream iterations (retuning thresholds,
re-running discovery) never have to reload the bge-m3 model just to re-embed the
same fixed anchor set. The cache is keyed by a fingerprint of the anchor texts +
embedding settings, so any edit to the taxonomy or truncation settings triggers
a transparent rebuild.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class Anchor:
    key: str                       # e.g. "payment_gateway"
    path_keys: Tuple[str, ...]     # ("payments", "payment_gateway")
    level: int                     # 1 / 2 / 3
    name: str
    desc: str
    source: str                    # "seed" | "discovered"
    parent_key: Optional[str]      # None at L1
    breadcrumb: str                # "Payments > Payment Gateway"


def flatten_taxonomy(tax: Dict[str, dict]) -> List[Anchor]:
    """Depth-first flatten of the taxonomy into a list of anchors.

    Order is deterministic (dict insertion order, depth-first), so anchor row i
    is stable across runs given the same taxonomy -- which matters because the
    matcher indexes anchor_vecs by position.
    """
    anchors: List[Anchor] = []

    def rec(node_map: Dict[str, dict], depth: int,
            path_keys: Tuple[str, ...], name_path: Tuple[str, ...],
            parent_key: Optional[str]) -> None:
        for key, spec in node_map.items():
            here_keys = path_keys + (key,)
            here_names = name_path + (spec["name"],)
            anchors.append(
                Anchor(
                    key=key,
                    path_keys=here_keys,
                    level=depth,
                    name=spec["name"],
                    desc=spec["desc"],
                    source=spec.get("source", "seed"),
                    parent_key=parent_key,
                    breadcrumb=" > ".join(here_names),
                )
            )
            children = spec.get("children", {})
            if children:
                rec(children, depth + 1, here_keys, here_names, key)

    rec(tax, 1, (), (), None)
    return anchors


def anchor_text(a: Anchor, include_breadcrumb: bool = True) -> str:
    """The string handed to bge-m3 for this anchor."""
    if include_breadcrumb:
        return f"{a.breadcrumb}: {a.desc}"
    return a.desc


def anchors_by_level(anchors: List[Anchor]) -> Dict[int, List[int]]:
    """Map level -> list of anchor row indices at that level."""
    out: Dict[int, List[int]] = {1: [], 2: [], 3: []}
    for i, a in enumerate(anchors):
        out.setdefault(a.level, []).append(i)
    return out


def children_index(anchors: List[Anchor]) -> Dict[Optional[str], List[int]]:
    """Map parent_key -> list of anchor row indices of its direct children.

    ``None`` maps to the L1 anchors. Used by the matcher to restrict the L2/L3
    argmax to the children of the level above.
    """
    out: Dict[Optional[str], List[int]] = {}
    for i, a in enumerate(anchors):
        out.setdefault(a.parent_key, []).append(i)
    return out


def _fingerprint(texts: List[str], embed_fingerprint: dict) -> str:
    h = hashlib.sha256()
    h.update(repr(sorted(embed_fingerprint.items())).encode("utf-8"))
    h.update(str(len(texts)).encode())
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:32]


def embed_anchors(
    embedder,
    anchors: List[Anchor],
    cache_path: str,
    *,
    include_breadcrumb: bool = True,
    embed_fingerprint: Optional[dict] = None,
) -> np.ndarray:
    """Return an [n_anchors, dim] float32 L2-normalised matrix, cached to npz.

    The cache stores the fingerprint alongside the vectors; a mismatch (taxonomy
    edited, truncation changed) rebuilds transparently instead of returning
    stale vectors.
    """
    texts = [anchor_text(a, include_breadcrumb) for a in anchors]
    fp = _fingerprint(texts, embed_fingerprint or {})

    if os.path.exists(cache_path):
        try:
            cached = np.load(cache_path, allow_pickle=False)
            if str(cached.get("fingerprint")) == fp and int(cached["vectors"].shape[0]) == len(texts):
                vecs = cached["vectors"].astype(np.float32)
                log.info("[anchors] loaded %d cached anchor vectors from %s",
                         vecs.shape[0], cache_path)
                return vecs
            log.info("[anchors] anchor cache stale (fingerprint/shape mismatch); rebuilding")
        except (OSError, KeyError, ValueError) as exc:
            log.warning("[anchors] could not read anchor cache (%s); rebuilding", exc)

    log.info("[anchors] embedding %d anchors (L1/L2/L3) ...", len(texts))
    vecs = embedder.encode_texts(texts)
    vecs = np.asarray(vecs, dtype=np.float32)

    _write_anchor_cache(cache_path, vecs, fp)
    return vecs


def _write_anchor_cache(cache_path: str, vecs: np.ndarray, fp: str) -> None:
    """Persist the anchor vectors to ``cache_path`` as robustly as possible.

    The cache is an optimisation, never correctness-critical: if it cannot be
    written we log a warning and carry on (the returned vectors are already
    correct, only the next run will have to re-embed). On Windows ``os.replace``
    over an existing target intermittently raises WinError 5 when antivirus, a
    file indexer, or a cloud-sync agent momentarily holds the destination open,
    so we:
      * write to a unique, correctly-suffixed (".npz") temp file with the handle
        fully closed + fsync'd before any rename;
      * retry the replace with backoff;
      * fall back to remove-then-rename;
      * finally fall back to writing straight to the target;
      * and if all of that fails, just warn -- never crash the caller.
    """
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    tmp = f"{cache_path}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp.npz"
    try:
        with open(tmp, "wb") as fh:
            np.savez(fh, vectors=vecs, fingerprint=np.array(fp))
            fh.flush()
            os.fsync(fh.fileno())

        # Try an atomic replace, retrying through transient Windows locks.
        last_exc: Optional[OSError] = None
        for attempt in range(5):
            try:
                os.replace(tmp, cache_path)
                log.info("[anchors] wrote %d anchor vectors -> %s",
                         vecs.shape[0], cache_path)
                return
            except OSError as exc:  # WinError 5 etc.
                last_exc = exc
                time.sleep(0.4 * (attempt + 1))

        # Fallback 1: remove the target first, then rename.
        try:
            if os.path.exists(cache_path):
                os.remove(cache_path)
            os.replace(tmp, cache_path)
            log.info("[anchors] wrote %d anchor vectors -> %s (after remove)",
                     vecs.shape[0], cache_path)
            return
        except OSError as exc:
            last_exc = exc

        # Fallback 2: write directly to the target (non-atomic, last resort).
        try:
            with open(cache_path, "wb") as fh:
                np.savez(fh, vectors=vecs, fingerprint=np.array(fp))
                fh.flush()
                os.fsync(fh.fileno())
            log.info("[anchors] wrote %d anchor vectors -> %s (direct)",
                     vecs.shape[0], cache_path)
            return
        except OSError as exc:
            last_exc = exc

        log.warning(
            "[anchors] could not persist anchor cache to %s (%s); continuing "
            "without caching -- the next run will re-embed the anchors. This is "
            "usually antivirus / a file indexer / cloud-sync holding the file "
            "open; excluding the work/ dir from those tools removes the warning.",
            cache_path, last_exc,
        )
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
