"""Content-addressed embedding cache backed by SQLite.

Why this exists
---------------
The positional shard cache keys embeddings by *manifest row position* and is
invalidated whenever the manifest fingerprint changes. So growing the manifest
(e.g. 23k -> 100k) throws away every shard even though most documents were
already embedded. This layer sits *under* the positional shards and reuses an
embedding whenever the exact text that would be fed to bge-m3 has been seen
before, regardless of which manifest/row/path it came from.

Identity
--------
The cache key is derived ONLY from what actually affects the embedding value:

    content_hash = sha256(rendered_embed_text)
    cache_key    = sha256(content_hash + embedding_config_fingerprint)

No path, no doc_id, no manifest row, no manifest fingerprint participates. Two
documents that render to the same embed_text share a vector; a document whose
content (and therefore rendered text) changes gets a new key and is recomputed;
changing any embedding-config parameter (model, truncation, repeat-title, fp16,
...) changes the fingerprint and therefore every key, so stale vectors are never
reused across incompatible configs.

Scope
-----
This module only stores and retrieves vectors by content key. It does not touch
the positional shard files, the manifest, or any downstream logic. It is safe to
delete ``work/vector_store.sqlite``: the next run simply recomputes misses.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

log = logging.getLogger(__name__)

# Stored vectors use the same on-disk dtype as the positional shards (float16),
# so the content cache and the shard cache are numerically identical for a given
# text. Callers renormalise on load exactly as they already do for shards.
STORE_DTYPE = np.float16


def _config_fingerprint_str(embed_fingerprint: dict) -> str:
    """Stable string form of the embedding-config fingerprint dict."""
    return repr(sorted((str(k), str(v)) for k, v in embed_fingerprint.items()))


def content_hash(rendered_embed_text: str) -> str:
    """sha256 of the final text handed to the encoder."""
    return hashlib.sha256(rendered_embed_text.encode("utf-8")).hexdigest()


def cache_key(rendered_embed_text: str, embed_fingerprint: dict) -> str:
    """The content-addressed cache key: content + embedding configuration."""
    ch = content_hash(rendered_embed_text)
    h = hashlib.sha256()
    h.update(ch.encode("ascii"))
    h.update(b"|")
    h.update(_config_fingerprint_str(embed_fingerprint).encode("utf-8"))
    return h.hexdigest()


@dataclass
class CacheStats:
    """Counters for one embedding run (across all shards)."""
    positional_shard_hits: int = 0     # documents covered by reused shards
    content_cache_hits: int = 0        # documents served from SQLite
    cache_misses: int = 0              # documents newly encoded by bge-m3

    @property
    def newly_encoded(self) -> int:
        return self.cache_misses

    @property
    def content_lookups(self) -> int:
        return self.content_cache_hits + self.cache_misses

    @property
    def content_hit_rate(self) -> float:
        n = self.content_lookups
        return (self.content_cache_hits / n) if n else 0.0

    def log_summary(self) -> None:
        log.info("[cache] Embedding cache:")
        log.info("[cache]   positional shard hits: %d", self.positional_shard_hits)
        log.info("[cache]   content cache hits:    %d", self.content_cache_hits)
        log.info("[cache]   cache misses:          %d", self.cache_misses)
        log.info("[cache]   newly encoded:         %d", self.newly_encoded)
        log.info("[cache]   content cache hit rate: %.1f%%", 100.0 * self.content_hit_rate)


class VectorStore:
    """Thin SQLite wrapper for content-addressed embedding vectors."""

    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS embeddings (
                cache_key  TEXT PRIMARY KEY,
                vector     BLOB NOT NULL,
                dim        INTEGER NOT NULL,
                dtype      TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    # -- lookup ------------------------------------------------------------

    def get_many(self, keys: Sequence[str]) -> Dict[str, np.ndarray]:
        """Return {key: vector} for the keys present in the store.

        Vectors are returned as float32 (upcast from the stored float16) so the
        assembled matrix matches what a fresh encode + shard round-trip yields.
        """
        out: Dict[str, np.ndarray] = {}
        if not keys:
            return out
        # De-duplicate while preserving lookup by key.
        unique = list(dict.fromkeys(keys))
        CHUNK = 900  # stay under SQLite's variable limit
        for i in range(0, len(unique), CHUNK):
            batch = unique[i:i + CHUNK]
            placeholders = ",".join("?" * len(batch))
            rows = self._conn.execute(
                f"SELECT cache_key, vector, dim, dtype FROM embeddings "
                f"WHERE cache_key IN ({placeholders})",
                batch,
            ).fetchall()
            for key, blob, dim, dtype in rows:
                vec = np.frombuffer(blob, dtype=np.dtype(dtype)).reshape(dim)
                out[key] = vec.astype(np.float32)
        return out

    # -- write -------------------------------------------------------------

    def put_many(self, items: Sequence[tuple]) -> None:
        """Insert (key, vector) pairs. Existing keys are left unchanged.

        Vectors are stored in STORE_DTYPE (float16) to match the positional
        shard on-disk precision.
        """
        if not items:
            return
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        payload = []
        for key, vec in items:
            v = np.asarray(vec, dtype=STORE_DTYPE)
            payload.append((key, v.tobytes(), int(v.shape[0]), np.dtype(STORE_DTYPE).name, now))
        self._conn.executemany(
            "INSERT OR IGNORE INTO embeddings (cache_key, vector, dim, dtype, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            payload,
        )
        self._conn.commit()

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self) -> "VectorStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
