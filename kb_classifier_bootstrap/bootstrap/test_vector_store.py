"""Tests for the content-addressed embedding cache.

Run:
    python -m kb_classifier_bootstrap.bootstrap.test_vector_store

These use a deterministic fake encoder (a hash-seeded RNG per text) instead of
bge-m3, so they are fast and hermetic while still exercising the exact cache
key, lookup, reuse, and matrix-assembly logic used in production. The final test
also drives the real ``embed_corpus_resumable`` pass to prove the assembled
positional-shard matrix is identical with and without the content cache.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from typing import List, Sequence

import numpy as np

from .corpus import Document, ManifestEntry
from .embedder import embed_corpus_resumable, load_all_embeddings
from .vector_store import CacheStats, VectorStore, cache_key


# --------------------------------------------------------------------------
# fakes
# --------------------------------------------------------------------------

DIM = 16


class FakeEmbedder:
    """Same surface as BgeM3Embedder for the bits the cache path touches.

    encode_texts is deterministic in the text (seeded by its hash), so a given
    text always yields the same vector -- lets us assert numerical equality.
    """

    def __init__(self, body_char_budget=2000, repeat_title=True):
        self.body_char_budget = body_char_budget
        self.repeat_title = repeat_title
        self._dim = DIM
        self.encode_calls: List[int] = []   # records batch sizes for assertions

    class _Cfg:
        pass

    @property
    def dim(self):
        return self._dim

    def _vec_for(self, text: str) -> np.ndarray:
        seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(DIM).astype(np.float32)
        v /= np.linalg.norm(v)
        return v

    def encode_texts(self, texts: Sequence[str], batch_size=None) -> np.ndarray:
        self.encode_calls.append(len(texts))
        if not texts:
            return np.zeros((0, DIM), dtype=np.float32)
        return np.stack([self._vec_for(t) for t in texts])

    def render_embed_texts(self, docs: Sequence[Document]) -> List[str]:
        return [d.embed_text(self.body_char_budget, self.repeat_title) for d in docs]

    # copied verbatim behaviour from BgeM3Embedder.encode_documents_cached
    def encode_documents_cached(self, docs, store, embed_fingerprint, stats):
        texts = self.render_embed_texts(docs)
        keys = [cache_key(t, embed_fingerprint) for t in texts]
        cached = store.get_many(keys)
        stats.content_cache_hits += sum(1 for k in keys if k in cached)
        miss = {}
        for k, t in zip(keys, texts):
            if k not in cached and k not in miss:
                miss[k] = t
        if miss:
            mk = list(miss)
            mv = self.encode_texts([miss[k] for k in mk])
            store.put_many(list(zip(mk, mv)))
            for k, v in zip(mk, mv):
                cached[k] = np.asarray(v, dtype=np.float32)
            stats.cache_misses += sum(1 for k in keys if k in miss)
        out = np.empty((len(docs), self.dim), dtype=np.float32)
        for i, k in enumerate(keys):
            out[i] = cached[k]
        return out

    def total_texts_encoded(self) -> int:
        return sum(self.encode_calls)


FP = {"model_name": "fake", "max_seq_length": 512, "repeat_title": True}


def _doc(idx: int, title: str, body: str) -> Document:
    return Document(doc_index=idx, doc_id=f"d{idx}", rel_path=f"p/{title}.txt",
                    stratum="p", source="p", title=title, body=body)


def _docs_from(specs) -> List[Document]:
    return [_doc(i, t, b) for i, (t, b) in enumerate(specs)]


# --------------------------------------------------------------------------
# tests over encode_documents_cached (Cases 1-5)
# --------------------------------------------------------------------------

def test_reorder_reuse(tmp):
    """Test 1: same docs reordered -> all reused, 0 re-encoded on second run."""
    store_path = os.path.join(tmp, "vs1.sqlite")
    A = _docs_from([("doc1", "b1"), ("doc2", "b2"), ("doc3", "b3")])
    with VectorStore(store_path) as vs:
        e = FakeEmbedder(); st = CacheStats()
        e.encode_documents_cached(A, vs, FP, st)
        assert st.cache_misses == 3 and st.content_cache_hits == 0

    B = [A[2], A[0], A[1]]  # reordered
    with VectorStore(store_path) as vs:
        e = FakeEmbedder(); st = CacheStats()
        e.encode_documents_cached(B, vs, FP, st)
        assert st.content_cache_hits == 3, st
        assert st.cache_misses == 0, st
        assert e.total_texts_encoded() == 0
    print("Test 1 (reorder reuse): OK")


def test_add_docs(tmp):
    """Test 2: adding docs -> only new ones encoded."""
    store_path = os.path.join(tmp, "vs2.sqlite")
    A = _docs_from([("doc1", "b1"), ("doc2", "b2"), ("doc3", "b3")])
    with VectorStore(store_path) as vs:
        FakeEmbedder().encode_documents_cached(A, vs, FP, CacheStats())
    B = A + _docs_from([("doc4", "b4"), ("doc5", "b5")])
    for i, d in enumerate(B):
        d.doc_index = i
    with VectorStore(store_path) as vs:
        e = FakeEmbedder(); st = CacheStats()
        e.encode_documents_cached(B, vs, FP, st)
        assert st.content_cache_hits == 3, st
        assert st.cache_misses == 2, st
    print("Test 2 (add docs): OK")


def test_remove_docs(tmp):
    """Test 3: removing docs -> remaining reused, none recomputed."""
    store_path = os.path.join(tmp, "vs3.sqlite")
    A = _docs_from([("doc1", "b1"), ("doc2", "b2"), ("doc3", "b3")])
    with VectorStore(store_path) as vs:
        FakeEmbedder().encode_documents_cached(A, vs, FP, CacheStats())
    B = [A[0], A[2]]  # dropped doc2
    with VectorStore(store_path) as vs:
        e = FakeEmbedder(); st = CacheStats()
        e.encode_documents_cached(B, vs, FP, st)
        assert st.content_cache_hits == 2 and st.cache_misses == 0, st
        assert e.total_texts_encoded() == 0
    print("Test 3 (remove docs): OK")


def test_content_change_misses(tmp):
    """Test 4: same path, changed content -> cache miss, recompute."""
    store_path = os.path.join(tmp, "vs4.sqlite")
    old = [_doc(0, "doc1", "original body")]
    with VectorStore(store_path) as vs:
        FakeEmbedder().encode_documents_cached(old, vs, FP, CacheStats())
    new = [_doc(0, "doc1", "COMPLETELY DIFFERENT body")]  # same path, new text
    with VectorStore(store_path) as vs:
        e = FakeEmbedder(); st = CacheStats()
        e.encode_documents_cached(new, vs, FP, st)
        assert st.cache_misses == 1 and st.content_cache_hits == 0, st
    print("Test 4 (content change misses): OK")


def test_config_change_misses(tmp):
    """Test 5: same text, changed embedding config -> cache miss."""
    store_path = os.path.join(tmp, "vs5.sqlite")
    A = _docs_from([("doc1", "b1")])
    with VectorStore(store_path) as vs:
        FakeEmbedder().encode_documents_cached(A, vs, FP, CacheStats())
    fp2 = dict(FP, max_seq_length=256)  # a config parameter changed
    with VectorStore(store_path) as vs:
        e = FakeEmbedder(); st = CacheStats()
        e.encode_documents_cached(A, vs, fp2, st)
        assert st.cache_misses == 1 and st.content_cache_hits == 0, st
    # and the original key still hits under the original fingerprint
    with VectorStore(store_path) as vs:
        e = FakeEmbedder(); st = CacheStats()
        e.encode_documents_cached(A, vs, FP, st)
        assert st.content_cache_hits == 1, st
    print("Test 5 (config change misses): OK")


# --------------------------------------------------------------------------
# Test 6: assembled-matrix correctness through the real resumable pass
# --------------------------------------------------------------------------

def _write_manifest(path: str, docs: List[Document]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for i, d in enumerate(docs):
            e = ManifestEntry(doc_index=i, doc_id=d.doc_id, rel_path=d.rel_path,
                              stratum=d.stratum, source=d.source, title=d.title)
            f.write(e.to_json() + "\n")


def _write_corpus(root: str, docs: List[Document]) -> None:
    for d in docs:
        full = os.path.join(root, d.rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(d.title + "\n" + d.body)


def test_assembled_matrix_matches(tmp):
    """Test 6: matrix from content-cache reuse == from-scratch matrix."""
    from .corpus import load_manifest, manifest_fingerprint

    root = os.path.join(tmp, "corpus")
    all_docs = _docs_from([(f"doc{i}", f"body number {i}") for i in range(12)])
    _write_corpus(root, all_docs)

    def run(embed_dir, store_path, docs):
        man = os.path.join(embed_dir, "manifest.jsonl")
        _write_manifest(man, docs)
        entries = load_manifest(man)
        e = FakeEmbedder()
        st = CacheStats()
        embed_corpus_resumable(
            embedder=e, corpus_root=root, entries=entries,
            embed_dir=embed_dir, state_path=os.path.join(embed_dir, "state.json"),
            embed_fingerprint=FP, manifest_fingerprint=manifest_fingerprint(entries),
            shard_size=5, vector_store_path=store_path, cache_stats=st,
        )
        mat = load_all_embeddings(embed_dir, len(entries), 5)
        return mat, st

    # Manifest A: docs 0..7
    store = os.path.join(tmp, "shared_vs.sqlite")
    A = all_docs[:8]
    matA, _ = run(os.path.join(tmp, "runA"), store, A)

    # Manifest B: reordered + added (8,9) + removed (drop 2,5), sharing the store
    B = [all_docs[7], all_docs[0], all_docs[3], all_docs[8],
         all_docs[9], all_docs[1], all_docs[6], all_docs[4]]
    for i, d in enumerate(B):
        d.doc_index = i
    matB_cached, stB = run(os.path.join(tmp, "runB"), store, B)

    # From-scratch B with a FRESH empty store -> ground truth.
    matB_scratch, _ = run(os.path.join(tmp, "runB2"), os.path.join(tmp, "fresh_vs.sqlite"), B)

    assert matB_cached.shape == matB_scratch.shape
    assert np.allclose(matB_cached, matB_scratch, atol=1e-3), \
        f"max abs diff {np.abs(matB_cached - matB_scratch).max()}"

    # B reused docs {7,0,3,1,6,4} from A's store; only {8,9} were new.
    assert stB.content_cache_hits == 6, stB
    assert stB.cache_misses == 2, stB
    print("Test 6 (assembled matrix matches; cross-manifest reuse): OK")


def test_positional_shard_untouched(tmp):
    """Positional shard still directly reused when manifest is unchanged."""
    from .corpus import load_manifest, manifest_fingerprint

    root = os.path.join(tmp, "corpusP")
    docs = _docs_from([(f"d{i}", f"body {i}") for i in range(6)])
    _write_corpus(root, docs)
    embed_dir = os.path.join(tmp, "runP")
    man = os.path.join(embed_dir, "manifest.jsonl")
    _write_manifest(man, docs)
    entries = load_manifest(man)
    store = os.path.join(tmp, "vsP.sqlite")

    e1 = FakeEmbedder(); st1 = CacheStats()
    embed_corpus_resumable(
        embedder=e1, corpus_root=root, entries=entries, embed_dir=embed_dir,
        state_path=os.path.join(embed_dir, "state.json"), embed_fingerprint=FP,
        manifest_fingerprint=manifest_fingerprint(entries), shard_size=3,
        vector_store_path=store, cache_stats=st1)
    assert st1.cache_misses == 6

    # Second run, same manifest: shards already on disk -> positional hits,
    # no content lookups, no encoding.
    e2 = FakeEmbedder(); st2 = CacheStats()
    embed_corpus_resumable(
        embedder=e2, corpus_root=root, entries=entries, embed_dir=embed_dir,
        state_path=os.path.join(embed_dir, "state.json"), embed_fingerprint=FP,
        manifest_fingerprint=manifest_fingerprint(entries), shard_size=3,
        vector_store_path=store, cache_stats=st2)
    assert st2.positional_shard_hits == 6, st2
    assert st2.content_cache_hits == 0 and st2.cache_misses == 0, st2
    assert e2.total_texts_encoded() == 0
    print("Positional-shard reuse unaffected: OK")


def main():
    tmp = tempfile.mkdtemp(prefix="vscache_test_")
    try:
        test_reorder_reuse(tmp)
        test_add_docs(tmp)
        test_remove_docs(tmp)
        test_content_change_misses(tmp)
        test_config_change_misses(tmp)
        test_assembled_matrix_matches(tmp)
        test_positional_shard_untouched(tmp)
        print("\nALL VECTOR-STORE TESTS PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
