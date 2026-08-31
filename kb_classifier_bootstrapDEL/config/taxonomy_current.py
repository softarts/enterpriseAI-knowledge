"""Load the CURRENT taxonomy for a discovery round, with a T0 fallback.

The versioned discovery loop works like this each round:

    corpus scope N
      -> classify with the CURRENT taxonomy
      -> UNKNOWN
      -> HDBSCAN discovery
      -> LLM naming
      -> a COMPLETE new taxonomy  (taxonomy_v{N}.py, and taxonomy.py = latest)

"Current taxonomy" is whatever the last round produced. This module resolves it
in priority order:

    1. the highest-numbered ``config/taxonomy_v<N>.py`` (the authoritative
       per-round artifact this loop writes);
    2. ``config/taxonomy.py`` (the "latest" pointer; also what older runs wrote
       before versioned files existed);
    3. ``SEED_TAXONOMY`` -- the T0 hand-written skeleton, used when no taxonomy
       has ever been generated (the very first round).

A new taxonomy does NOT need to inherit from the current one; the loop is free
to add, rename, drop or restructure nodes. The current taxonomy is loaded only
so this round's documents can be *classified* against it before discovery.
"""

from __future__ import annotations

import glob
import importlib.util
import logging
import os
import re
from typing import Dict, Optional, Tuple

from .settings import SETTINGS
from .taxonomy_seed import SEED_TAXONOMY, validate_taxonomy

log = logging.getLogger(__name__)

# Matches both legacy (taxonomy_v3.py) and sample-count (taxonomy_v4_100k.py)
# forms; group(1) is the integer version.
_VERSION_RE = re.compile(r"taxonomy_v(\d+)(?:_[^.]+)?\.py$")


def _load_taxonomy_from_file(path: str) -> Dict[str, dict]:
    """Import a taxonomy_*.py module by path and return its TAXONOMY dict."""
    spec = importlib.util.spec_from_file_location("_kb_current_taxonomy", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load taxonomy module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    tax = getattr(module, "TAXONOMY", None)
    if not isinstance(tax, dict) or not tax:
        raise ImportError(f"{path} does not define a non-empty TAXONOMY dict")
    return tax


def _taxonomy_path_for_version(config_dir: str, version: int) -> Optional[str]:
    """Path to the taxonomy file for ``version``, whatever its count suffix.

    Prefers the bare ``taxonomy_v<N>.py`` if present, else the sample-count form
    ``taxonomy_v<N>_<label>.py``. Returns None if no file for that version.
    """
    bare = os.path.join(config_dir, f"taxonomy_v{version}.py")
    if os.path.exists(bare):
        return bare
    suffixed = glob.glob(os.path.join(config_dir, f"taxonomy_v{version}_*.py"))
    return suffixed[0] if suffixed else None


def latest_taxonomy_version(config_dir: Optional[str] = None) -> int:
    """Highest N among existing config/taxonomy_v<N>.py, or 0 if none."""
    config_dir = config_dir or SETTINGS.paths.config_dir
    highest = 0
    for p in glob.glob(os.path.join(config_dir, "taxonomy_v*.py")):
        m = _VERSION_RE.search(os.path.basename(p))
        if m:
            highest = max(highest, int(m.group(1)))
    return highest


def load_current_taxonomy(
    config_dir: Optional[str] = None,
) -> Tuple[Dict[str, dict], str]:
    """Resolve and return (taxonomy, source_label).

    source_label is a human-readable string for logs/reports, one of:
      "taxonomy_v<N>.py", "taxonomy.py", or "SEED_TAXONOMY (T0)".
    The returned taxonomy is structurally validated (3 levels, unique keys,
    non-empty descs) before being handed back.
    """
    paths = SETTINGS.paths
    config_dir = config_dir or paths.config_dir

    # 1. highest taxonomy_v<N>[_<count>].py
    n = latest_taxonomy_version(config_dir)
    if n > 0:
        path = _taxonomy_path_for_version(config_dir, n)
        if path is not None:
            try:
                tax = _load_taxonomy_from_file(path)
                validate_taxonomy(tax)
                label = os.path.basename(path)
                log.info("[taxonomy] current taxonomy = %s", label)
                return tax, label
            except Exception as exc:  # noqa: BLE001 - fall through to next source
                log.warning("[taxonomy] failed to load %s (%s); trying taxonomy.py",
                            path, exc)

    # 2. taxonomy.py (latest pointer / legacy output)
    if os.path.exists(paths.taxonomy_out_path):
        try:
            tax = _load_taxonomy_from_file(paths.taxonomy_out_path)
            validate_taxonomy(tax)
            log.info("[taxonomy] current taxonomy = taxonomy.py")
            return tax, "taxonomy.py"
        except Exception as exc:  # noqa: BLE001 - fall through to seed
            log.warning("[taxonomy] failed to load taxonomy.py (%s); using SEED_TAXONOMY",
                        exc)

    # 3. T0 seed skeleton
    log.info("[taxonomy] no generated taxonomy found; current taxonomy = SEED_TAXONOMY (T0)")
    return SEED_TAXONOMY, "SEED_TAXONOMY (T0)"
