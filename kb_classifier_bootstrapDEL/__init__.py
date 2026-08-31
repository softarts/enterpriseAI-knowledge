"""One-off Bootstrap (Stage A) taxonomy + threshold generator.

Stage A scans an initial batch of articles once and emits:
  * config/taxonomy.py     -- 3-level taxonomy (seed anchors + discovered nodes)
  * config/thresholds.json -- per-level match thresholds
  * bootstrap_report.md    -- what happened, so the run is auditable

Stage B (per-article rule-based classification at import time) is out of scope
here and consumes these artifacts read-only.
"""
