"""Shared code used by both Stage A (bootstrap) and Stage B (per-article).

These modules implement the reusable classification primitives:

* ``corpus``       -- corpus scan, document parsing, frozen manifest
* ``embedder``     -- resumable bge-m3 embedding + content-addressed cache
* ``vector_store`` -- content-addressed embedding cache (SQLite)
* ``anchors``      -- flatten a taxonomy into embeddable anchors (+ cache)
* ``matching``     -- hierarchical L1->L2->L3 nearest-anchor matching

Stage A adds threshold fitting, gap discovery, LLM naming and taxonomy
emission on top of these; Stage B reuses ``anchors`` + ``matching`` only.
"""
