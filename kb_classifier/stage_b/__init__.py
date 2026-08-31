"""Stage B: per-article, rule-based classification at import time.

Consumes the frozen Stage A artifacts (``config/taxonomy.py`` +
``config/thresholds.json``) read-only and assigns each document a three-level
path via the same hierarchical nearest-anchor matching used in bootstrap. No
clustering and no LLM calls -- each document is a handful of dot products.
"""
