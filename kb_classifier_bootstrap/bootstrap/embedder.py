"""Resumable bge-m3 embedding with on-disk shard checkpoints.

Why this exists
---------------
The bootstrap corpus is ~512k documents and the available GPU is a 4 GB Quadro
T1000. A full pass is a multi-hour to multi-day job, so it must survive being
interrupted -- by Ctrl-C, a reboot, or simply wanting the machine back.

Resumability contract
---------------------
* ``manifest.jsonl`` is frozen first, so manifest row ``i`` is permanently the
  same article. Shards are keyed by row range, not by discovery order.
* Each shard is written to ``shard_<start>.npy.tmp`` and then atomically
  renamed. A crash mid-write therefore leaves a ``.tmp`` file that is ignored
  and recomputed -- a partially written shard can never be mistaken for a
  complete one.
* ``state.json`` records the embedding fingerprint (model, truncation, dtype,
  shard size) and the manifest fingerprint. If either changed, resuming would
  silently mix incompatible vectors, so we refuse instead.
* Progress is therefore derived from the filesystem, not from a counter that
  could disagree with reality.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from ..config.settings import EmbeddingSettings
from .corpus import Document, ManifestEntry, iter_documents

log = logging.getLogger(__name__)

_SHARD_RE = re.compile(r"^shard_(\d+)\.npy$")
EMBED_DTYPE = np.float16


# ---------------------------------------------------------------------------
# shard bookkeeping
# ---------------------------------------------------------------------------


@dataclass
class ShardPlan:
    start: int
    end: int          # exclusive

    @property
    def count(self) -> int:
        return self.end - self.start


def plan_shards(n_docs: int, shard_size: int) -> List[ShardPlan]:
    return [
        ShardPlan(start=s, end=min(s + shard_size, n_docs))
        for s in range(0, n_docs, shard_size)
    ]


def shard_path(embed_dir: str, start: int) -> str:
    return os.path.join(embed_dir, f"shard_{start:09d}.npy")


def existing_shard_starts(embed_dir: str) -> Dict[int, str]:
    """Map shard start row -> path, for every *completed* shard on disk."""
    out: Dict[int, str] = {}
    if not os.path.isdir(embed_dir):
        return out
    for fn in os.listdir(embed_dir):
        m = _SHARD_RE.match(fn)
        if m:
            out[int(m.group(1))] = os.path.join(embed_dir, fn)
    return out


def _cleanup_tmp(embed_dir: str) -> int:
    """Remove leftover .tmp shards from an interrupted run."""
    removed = 0
    if not os.path.isdir(embed_dir):
        return 0
    for fn in os.listdir(embed_dir):
        if fn.endswith(".npy.tmp"):
            try:
                os.remove(os.path.join(embed_dir, fn))
                removed += 1
            except OSError:
                pass
    return removed


# ---------------------------------------------------------------------------
# state file
# ---------------------------------------------------------------------------


class CacheStateError(RuntimeError):
    """Raised when an existing cache is incompatible with the current config."""


def _load_state(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def read_cached_shard_size(state_path: str) -> Optional[int]:
    """Shard size the existing cache was built with, if there is one.

    shard_size is a property of the cache layout, not a runtime knob: reading it
    back means callers never have to remember which value they used. Trusting a
    CLI default instead would mis-count completed shards and could report a
    partial cache as COMPLETE.
    """
    state = _load_state(state_path)
    if not state:
        return None
    size = (state.get("embedding") or {}).get("shard_size")
    return int(size) if size else None


def _write_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def verify_or_init_state(
    state_path: str,
    embed_fingerprint: dict,
    manifest_fingerprint: str,
    n_docs: int,
    embedding_dim: Optional[int] = None,
    prefix_fingerprint_at: Optional[Callable[[int], str]] = None,
) -> dict:
    """Load and validate the cache state, or create it on first run.

    ``prefix_fingerprint_at(k)`` (optional) returns the fingerprint of the
    current manifest's first ``k`` rows. When provided, a manifest that is a
    strict *prefix-extension* of the cached one is accepted (the cache's shards
    all live within the unchanged prefix, so they stay valid). Without it, only
    an exactly-identical manifest resumes -- the original strict behaviour.
    """
    desired = {
        "embedding": embed_fingerprint,
        "manifest_fingerprint": manifest_fingerprint,
        "n_docs": n_docs,
    }
    existing = _load_state(state_path)
    if existing is None:
        state = dict(desired)
        state["embedding_dim"] = embedding_dim
        state["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _write_state(state_path, state)
        log.info("[embed] initialised new embedding cache state at %s", state_path)
        return state

    mismatches = []
    if existing.get("embedding") != embed_fingerprint:
        mismatches.append(
            f"embedding settings changed: cached={existing.get('embedding')} "
            f"current={embed_fingerprint}"
        )

    cached_fp = existing.get("manifest_fingerprint")
    cached_n = int(existing.get("n_docs", 0))
    manifest_ok = cached_fp == manifest_fingerprint
    extended = False
    if not manifest_ok and prefix_fingerprint_at is not None and 0 < cached_n <= n_docs:
        # Accept a manifest whose first cached_n rows match the cached set.
        if prefix_fingerprint_at(cached_n) == cached_fp:
            manifest_ok = True
            extended = True
    if not manifest_ok:
        mismatches.append(
            "manifest changed (different document set or ordering): "
            f"cached={cached_fp} current={manifest_fingerprint}"
        )
    if mismatches:
        raise CacheStateError(
            "Cannot resume the existing embedding cache:\n  - "
            + "\n  - ".join(mismatches)
            + "\nResuming would mix incompatible vectors. Either restore the "
              "previous settings, or delete the embeddings directory to start "
              "a fresh pass."
        )

    if extended:
        log.info("[embed] existing cache covers the first %d of %d documents; the "
                 "manifest is a valid prefix-extension, reusing those shards",
                 cached_n, n_docs)
        # Advance the recorded manifest identity to the (larger) current one.
        existing["manifest_fingerprint"] = manifest_fingerprint
        existing["n_docs"] = n_docs
        existing["complete"] = False
        _write_state(state_path, existing)

    if embedding_dim is not None and existing.get("embedding_dim") is None:
        existing["embedding_dim"] = embedding_dim
        _write_state(state_path, existing)
    log.info("[embed] resuming existing embedding cache (%s)", state_path)
    return existing


# ---------------------------------------------------------------------------
# model wrapper
# ---------------------------------------------------------------------------


class BgeM3Embedder:
    """Thin, lazily-loaded wrapper around sentence-transformers bge-m3.

    Loading is deferred so that a fully-cached resume (nothing left to embed)
    never pays the multi-second model load, and so that --dry-run works on a
    machine without the weights.
    """

    def __init__(self, cfg: EmbeddingSettings) -> None:
        self.cfg = cfg
        self._model = None
        self._dim: Optional[int] = None
        self._device: Optional[str] = None

    def _resolve_device(self) -> str:
        if self.cfg.device != "auto":
            return self.cfg.device
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            # Apple Silicon (M-series) GPU. bge-m3 runs several times faster on
            # MPS than on the CPU, which matters on this CUDA-less Mac.
            if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
                return "mps"
            return "cpu"
        except ImportError:
            return "cpu"

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            device = self._resolve_device()
            self._device = device
            t0 = time.time()
            log.info(
                "[embed] loading %s on %s (fp16=%s) ...",
                self.cfg.model_name,
                device,
                self.cfg.use_fp16 and device == "cuda",
            )
            model = SentenceTransformer(self.cfg.model_name, device=device)
            model.max_seq_length = self.cfg.max_seq_length
            if self.cfg.use_fp16 and device == "cuda":
                # halves activation memory; bge-m3 in fp16 fits a 4 GB card at
                # 512 tokens where fp32 does not
                model = model.half()
            self._model = model
            self._dim = model.get_sentence_embedding_dimension()
            log.info(
                "[embed] model ready in %.1fs (dim=%d, max_seq_length=%d)",
                time.time() - t0,
                self._dim,
                self.cfg.max_seq_length,
            )
        return self._model

    @property
    def dim(self) -> int:
        if self._dim is None:
            _ = self.model
        assert self._dim is not None
        return self._dim

    @property
    def device(self) -> str:
        if self._device is None:
            _ = self.model
        assert self._device is not None
        return self._device

    def encode_texts(self, texts: Sequence[str], batch_size: Optional[int] = None) -> np.ndarray:
        """Encode to L2-normalised float32 vectors."""
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vecs = self.model.encode(
            list(texts),
            batch_size=batch_size or self.cfg.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,   # cosine similarity == dot product
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)

    def encode_documents(self, docs: Sequence[Document]) -> np.ndarray:
        texts = [
            d.embed_text(self.cfg.body_char_budget, self.cfg.repeat_title) for d in docs
        ]
        return self.encode_texts(texts)

    def render_embed_texts(self, docs: Sequence[Document]) -> List[str]:
        """The exact texts fed to bge-m3 for these documents.

        This is the single source of truth for the content-addressed cache key,
        so the cache always hashes what the encoder actually sees.
        """
        return [
            d.embed_text(self.cfg.body_char_budget, self.cfg.repeat_title) for d in docs
        ]

    def encode_documents_cached(
        self,
        docs: Sequence[Document],
        store: "VectorStore",
        embed_fingerprint: dict,
        stats: "CacheStats",
    ) -> np.ndarray:
        """Encode a batch of documents, reusing content-cached vectors.

        For each document the final rendered embed_text is hashed together with
        the embedding-config fingerprint into a content key. Keys already in the
        store are reused; the rest are encoded by bge-m3, stored, and returned.
        The returned matrix is in row order of ``docs`` (float32, L2-normalised),
        identical to what ``encode_documents`` would return.

        Distinct rows that render to the *same* text (same key) still each get a
        row in the output, all pointing at the one cached/encoded vector.
        """
        from .vector_store import cache_key as _cache_key

        texts = self.render_embed_texts(docs)
        keys = [_cache_key(t, embed_fingerprint) for t in texts]

        cached = store.get_many(keys)
        stats.content_cache_hits += sum(1 for k in keys if k in cached)

        # Encode the unique missing texts once each.
        miss_key_to_text: dict = {}
        for k, t in zip(keys, texts):
            if k not in cached and k not in miss_key_to_text:
                miss_key_to_text[k] = t

        if miss_key_to_text:
            miss_keys = list(miss_key_to_text.keys())
            miss_texts = [miss_key_to_text[k] for k in miss_keys]
            new_vecs = self.encode_texts(miss_texts)
            store.put_many(list(zip(miss_keys, new_vecs)))
            for k, v in zip(miss_keys, new_vecs):
                cached[k] = np.asarray(v, dtype=np.float32)
            # misses counts documents (rows) newly required, not unique texts,
            # so the total (hits + misses) equals len(docs).
            stats.cache_misses += sum(1 for k in keys if k in miss_key_to_text)

        dim = self.dim if self._dim is not None else next(iter(cached.values())).shape[0]
        out = np.empty((len(docs), dim), dtype=np.float32)
        for i, k in enumerate(keys):
            out[i] = cached[k]
        return out


# ---------------------------------------------------------------------------
# the resumable pass
# ---------------------------------------------------------------------------


@dataclass
class EmbedProgress:
    total_docs: int
    already_done: int
    newly_done: int
    shards_total: int
    shards_done_before: int
    shards_written: int
    elapsed_s: float
    docs_per_s: float
    complete: bool


def embed_corpus_resumable(
    *,
    embedder: BgeM3Embedder,
    corpus_root: str,
    entries: Sequence[ManifestEntry],
    embed_dir: str,
    state_path: str,
    embed_fingerprint: dict,
    manifest_fingerprint: str,
    shard_size: int,
    max_new_shards: Optional[int] = None,
    time_budget_s: Optional[float] = None,
    progress_cb: Optional[Callable[[int, int, float], None]] = None,
    prefix_fingerprint_at: Optional[Callable[[int], str]] = None,
    vector_store_path: Optional[str] = None,
    cache_stats: "Optional[CacheStats]" = None,
) -> EmbedProgress:
    """Embed every manifest row, skipping shards already on disk.

    Safe to call repeatedly: each call makes forward progress and can be stopped
    at any time. ``max_new_shards`` / ``time_budget_s`` let a caller do a bounded
    slice of work (used for benchmarking and for chunking a long run).
    """
    os.makedirs(embed_dir, exist_ok=True)

    n_removed = _cleanup_tmp(embed_dir)
    if n_removed:
        log.info("[embed] discarded %d partial shard(s) from a previous run", n_removed)

    verify_or_init_state(
        state_path,
        embed_fingerprint,
        manifest_fingerprint,
        len(entries),
        embedding_dim=None,
        prefix_fingerprint_at=prefix_fingerprint_at,
    )

    shards = plan_shards(len(entries), shard_size)
    have = existing_shard_starts(embed_dir)

    # Prefix-extension guard: an existing shard file is only reusable if it
    # holds exactly the number of rows the *new* shard plan expects at that
    # offset. When the manifest was extended and the previous last shard was
    # partial (cached_n not a multiple of shard_size), that boundary shard now
    # under-covers its new [start, start+shard_size) range; drop it so it is
    # recomputed with the correct neighbours instead of being trusted blindly.
    expected_count = {s.start: s.count for s in shards}
    stale = []
    for start, path in list(have.items()):
        if start not in expected_count:
            stale.append(start)
            continue
        try:
            rows = int(np.load(path, mmap_mode="r").shape[0])
        except (OSError, ValueError):
            rows = -1
        if rows != expected_count[start]:
            log.warning("[embed] shard at row %d has %d rows but the current plan "
                        "expects %d; discarding it for recomputation",
                        start, rows, expected_count[start])
            try:
                os.remove(path)
            except OSError:
                pass
            del have[start]
    for start in stale:
        log.warning("[embed] shard at row %d is outside the current shard plan; "
                    "leaving it untouched but ignoring it", start)
    todo = [s for s in shards if s.start not in have]
    done_docs = sum(
        min(shard_size, len(entries) - start) for start in have if start < len(entries)
    )

    # Content-addressed cache (sits UNDER the positional shards). Documents in
    # already-complete shards (Case A) are counted as positional-shard hits and
    # are NOT looked up in SQLite; only shards we must (re)compute (Case B) go
    # through the content cache.
    from .vector_store import CacheStats, VectorStore

    if cache_stats is None:
        cache_stats = CacheStats()
    cache_stats.positional_shard_hits += done_docs
    store = VectorStore(vector_store_path) if vector_store_path else None

    log.info(
        "[embed] %d/%d shards already complete (%d/%d documents, %.1f%%)",
        len(have),
        len(shards),
        done_docs,
        len(entries),
        100.0 * done_docs / max(len(entries), 1),
    )
    if not todo:
        log.info("[embed] nothing to do -- embedding cache is complete")
        return EmbedProgress(
            total_docs=len(entries),
            already_done=done_docs,
            newly_done=0,
            shards_total=len(shards),
            shards_done_before=len(have),
            shards_written=0,
            elapsed_s=0.0,
            docs_per_s=0.0,
            complete=True,
        )

    log.info("[embed] %d shard(s) remaining (~%d documents)",
             len(todo), sum(s.count for s in todo))

    t_start = time.time()
    written = 0
    new_docs = 0
    for plan in todo:
        if max_new_shards is not None and written >= max_new_shards:
            log.info("[embed] stopping: reached max_new_shards=%d", max_new_shards)
            break
        if time_budget_s is not None and (time.time() - t_start) >= time_budget_s:
            log.info("[embed] stopping: reached time budget of %.0fs", time_budget_s)
            break

        t0 = time.time()
        docs = list(iter_documents(corpus_root, entries, plan.start, plan.end))
        if store is not None:
            vecs = embedder.encode_documents_cached(
                docs, store, embed_fingerprint, cache_stats)
        else:
            vecs = embedder.encode_documents(docs)
        if vecs.shape[0] != plan.count:
            raise RuntimeError(
                f"shard [{plan.start},{plan.end}) produced {vecs.shape[0]} vectors, "
                f"expected {plan.count}"
            )

        out = shard_path(embed_dir, plan.start)
        tmp = out + ".tmp"
        # Write through an explicit file handle: np.save() appends ".npy" to any
        # path that does not already end in it, which would silently produce
        # "shard_x.npy.tmp.npy" and break the atomic rename below.
        with open(tmp, "wb") as fh:
            np.save(fh, vecs.astype(EMBED_DTYPE, copy=False))
        os.replace(tmp, out)

        written += 1
        new_docs += plan.count
        dt = time.time() - t0
        total_done = done_docs + new_docs
        rate = new_docs / max(time.time() - t_start, 1e-6)
        remaining = len(entries) - total_done
        eta_s = remaining / rate if rate > 0 else float("nan")
        log.info(
            "[embed] shard [%d,%d) %d docs in %.1fs (%.1f docs/s) | "
            "total %d/%d (%.1f%%) | rate %.1f docs/s | ETA %.1f min",
            plan.start,
            plan.end,
            plan.count,
            dt,
            plan.count / max(dt, 1e-6),
            total_done,
            len(entries),
            100.0 * total_done / max(len(entries), 1),
            rate,
            eta_s / 60.0,
        )
        if progress_cb is not None:
            progress_cb(total_done, len(entries), rate)

    elapsed = time.time() - t_start
    have_after = existing_shard_starts(embed_dir)
    complete = len(have_after) == len(shards)

    state = _load_state(state_path) or {}
    state["embedding_dim"] = embedder.dim if embedder._dim is not None else state.get("embedding_dim")
    state["last_run_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    state["shards_total"] = len(shards)
    state["shards_complete"] = len(have_after)
    state["complete"] = complete
    _write_state(state_path, state)

    if store is not None:
        log.info("[embed] content cache now holds %d vector(s)", store.count())
        store.close()
    cache_stats.log_summary()

    log.info(
        "[embed] pass finished: +%d docs in %.1fs (%.1f docs/s); cache %d/%d shards, complete=%s",
        new_docs,
        elapsed,
        new_docs / max(elapsed, 1e-6),
        len(have_after),
        len(shards),
        complete,
    )
    return EmbedProgress(
        total_docs=len(entries),
        already_done=done_docs,
        newly_done=new_docs,
        shards_total=len(shards),
        shards_done_before=len(have),
        shards_written=written,
        elapsed_s=elapsed,
        docs_per_s=new_docs / max(elapsed, 1e-6),
        complete=complete,
    )


def load_all_embeddings(
    embed_dir: str, n_docs: int, shard_size: int, dim: Optional[int] = None
) -> np.ndarray:
    """Assemble the full [n_docs, dim] float32 matrix from shards.

    Raises if any shard is missing, because silently zero-filling would corrupt
    every downstream threshold and cluster.
    """
    shards = plan_shards(n_docs, shard_size)
    have = existing_shard_starts(embed_dir)
    missing = [s for s in shards if s.start not in have]
    if missing:
        raise RuntimeError(
            f"embedding cache incomplete: {len(missing)}/{len(shards)} shards missing "
            f"(first missing starts at row {missing[0].start}). "
            "Re-run the embed stage to finish the pass."
        )

    first = np.load(have[shards[0].start])
    resolved_dim = dim or int(first.shape[1])
    out = np.empty((n_docs, resolved_dim), dtype=np.float32)
    out[shards[0].start : shards[0].end] = first.astype(np.float32)
    for plan in shards[1:]:
        arr = np.load(have[plan.start])
        if arr.shape[0] != plan.count or arr.shape[1] != resolved_dim:
            raise RuntimeError(
                f"shard {plan.start} has shape {arr.shape}, expected "
                f"({plan.count}, {resolved_dim})"
            )
        out[plan.start : plan.end] = arr.astype(np.float32)

    # fp16 round-trip perturbs unit norm slightly; renormalise so that dot
    # products remain exact cosine similarities.
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    np.divide(out, np.maximum(norms, 1e-12), out=out)
    log.info("[embed] loaded %d x %d embedding matrix from %d shards",
             out.shape[0], out.shape[1], len(shards))
    return out
