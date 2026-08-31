"""The merged seed taxonomy plus a structural validator.

``SEED_TAXONOMY`` is the hand-written 3-level skeleton: the business-line branch
(9 L1) and the functional branch (8 L1). The gap-discovery step later appends
``source: "discovered"`` nodes to a *copy* of this tree; the seed itself stays
immutable.

The validator enforces the invariants the whole pipeline relies on:
  * every node key is globally unique (keys become taxonomy identifiers and
    snake_case node names downstream);
  * the tree is exactly 3 levels deep -- L3 nodes have no children, and no
    branch is shallower than 3;
  * every node carries a non-empty ``name`` and ``desc`` (the desc is embedded,
    so an empty one is a silent recall hole).

Run this file directly for a quick self-check:
    python -m kb_classifier_bootstrap.config.taxonomy_seed
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .taxonomy_seed_business import BUSINESS_SEED
from .taxonomy_seed_functions import FUNCTION_SEED

SEED_TAXONOMY: Dict[str, dict] = {**BUSINESS_SEED, **FUNCTION_SEED}


class TaxonomyValidationError(ValueError):
    """Raised when the seed taxonomy violates a structural invariant."""


def _walk(tax: Dict[str, dict], depth: int, path: Tuple[str, ...],
          seen: Dict[str, Tuple[str, ...]], errors: List[str]) -> None:
    for key, spec in tax.items():
        here = path + (key,)

        if key in seen:
            errors.append(
                f"duplicate node key {key!r}: at {'/'.join(seen[key])} and "
                f"{'/'.join(here)}"
            )
        else:
            seen[key] = here

        name = spec.get("name")
        desc = spec.get("desc")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"node {'/'.join(here)} has empty/invalid name")
        if not isinstance(desc, str) or not desc.strip():
            errors.append(f"node {'/'.join(here)} has empty/invalid desc")

        children = spec.get("children", {})
        if depth < 3:
            if not isinstance(children, dict) or not children:
                errors.append(
                    f"node {'/'.join(here)} is at level {depth} but has no "
                    f"children; every branch must reach level 3"
                )
            else:
                _walk(children, depth + 1, here, seen, errors)
        else:  # depth == 3
            if children:
                errors.append(
                    f"node {'/'.join(here)} is at level 3 but has children "
                    f"(tree must be exactly 3 levels deep)"
                )


def validate_taxonomy(tax: Dict[str, dict] = SEED_TAXONOMY) -> None:
    """Raise TaxonomyValidationError if the tree breaks any invariant."""
    errors: List[str] = []
    seen: Dict[str, Tuple[str, ...]] = {}
    _walk(tax, 1, (), seen, errors)
    if errors:
        raise TaxonomyValidationError(
            f"seed taxonomy failed validation ({len(errors)} problem(s)):\n  - "
            + "\n  - ".join(errors)
        )


def count_by_level(tax: Dict[str, dict] = SEED_TAXONOMY) -> Dict[int, int]:
    """Return {1: n_l1, 2: n_l2, 3: n_l3}."""
    counts = {1: 0, 2: 0, 3: 0}

    def rec(node_map: Dict[str, dict], depth: int) -> None:
        for spec in node_map.values():
            counts[depth] = counts.get(depth, 0) + 1
            rec(spec.get("children", {}), depth + 1)

    rec(tax, 1)
    return counts


# Fail fast at import time: a malformed skeleton should never reach the pipeline.
validate_taxonomy(SEED_TAXONOMY)


if __name__ == "__main__":
    validate_taxonomy(SEED_TAXONOMY)
    counts = count_by_level(SEED_TAXONOMY)
    total = sum(counts.values())
    print("seed taxonomy OK")
    print(f"  L1 = {counts[1]}")
    print(f"  L2 = {counts[2]}")
    print(f"  L3 = {counts[3]}")
    print(f"  total nodes = {total}")
