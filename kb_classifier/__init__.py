"""Enterprise KB article classifier.

Layout:
  * common/    -- shared primitives (corpus, embedder, vector_store, anchors,
                  matching) used by both stages
  * config/    -- hyperparameters, seed taxonomy, generated taxonomy_v<N>.py,
                  the ``taxonomy.py`` latest-pointer and ``thresholds.json``
  * bootstrap/ -- Stage A only: threshold fitting, HDBSCAN gap discovery, LLM
                  naming, taxonomy emission, reporting (run via run_bootstrap.py)
  * stage_b/   -- Stage B: per-article rule-based classification that consumes
                  the frozen Stage A artifacts read-only (no clustering, no LLM)

Stage A scans a batch of articles and emits config/taxonomy.py,
config/thresholds.json and a versioned bootstrap report. Stage B reuses the
taxonomy + thresholds to assign each new document a three-level path.
"""
