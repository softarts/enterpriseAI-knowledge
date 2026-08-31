"""Emit the two config deliverables: taxonomy.py and thresholds.json.

``build_final_taxonomy`` starts from a deep copy of the immutable seed tree and
grafts each named discovered cluster onto its parent as a new child, tagged
``source: "discovered"``. Discovered L2 nodes get one placeholder child so the
emitted tree stays exactly three levels deep and importable by the same code
that reads the seed (Stage B expects a uniform shape).

``write_taxonomy_py`` serialises the merged tree to a real, importable Python
module via ``repr`` on plain dicts -- no pick_, no exec of model output. The file
is validated by re-importing it in run_bootstrap.

``write_thresholds_json`` writes the format the brief requires (L1/L2/L3 +
method_used) plus a diagnostics block carrying the GMM parameters and fallback
reasons, so Stage B can read the thresholds while a human can audit how they
were chosen.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
from typing import Dict, List, Optional

from ..config._node import DISCOVERED, SEED
from .discovery import DiscoveredCluster
from .naming import NamingResult
from .thresholds import ThresholdResult

log = logging.getLogger(__name__)


def _all_keys(tax: Dict[str, dict]) -> set:
    """Every node key anywhere in the tree."""
    out: set = set()

    def rec(node_map: Dict[str, dict]) -> None:
        for k, spec in node_map.items():
            out.add(k)
            rec(spec.get("children", {}))

    rec(tax)
    return out


def _keys_of_subtree(root_key: str, spec: dict) -> set:
    out = {root_key}

    def rec(node_map: Dict[str, dict]) -> None:
        for k, s in node_map.items():
            out.add(k)
            rec(s.get("children", {}))

    rec(spec.get("children", {}))
    return out


def _unique_key(desired: str, taken: set) -> str:
    key = desired
    n = 2
    while key in taken:
        key = f"{desired}_{n}"
        n += 1
    return key


def _find_node(tax: Dict[str, dict], key: str) -> Optional[dict]:
    """Locate a node dict by key anywhere in the tree (keys are unique)."""
    stack = list(tax.values())
    # We need the spec whose child key == key; search by walking with keys.
    def rec(node_map: Dict[str, dict]) -> Optional[dict]:
        for k, spec in node_map.items():
            if k == key:
                return spec
            found = rec(spec.get("children", {}))
            if found is not None:
                return found
        return None
    return rec(tax)


def _leaf(name: str, desc: str) -> dict:
    return {"name": name, "desc": desc, "source": DISCOVERED, "children": {}}


def _discovered_l2(node_key: str, name: str, desc: str) -> dict:
    """A discovered L2 node with exactly one placeholder L3 (keeps depth 3).

    The placeholder L3 key is derived from the L2 key so it is globally unique
    (``<key>_general``), never a bare ``general`` that collides across nodes.
    """
    return {
        "name": name,
        "desc": desc,
        "source": DISCOVERED,
        "children": {
            f"{node_key}_general": _leaf(
                f"{name} (General)",
                f"General documents within the discovered category '{name}'.",
            )
        },
    }


def _discovered_l3(name: str, desc: str) -> dict:
    return _leaf(name, desc)


def _discovered_l1(node_key: str, name: str, desc: str) -> dict:
    """A discovered L1 with one placeholder L2, which itself has one L3."""
    l2_key = f"{node_key}_general"
    return {
        "name": name,
        "desc": desc,
        "source": DISCOVERED,
        "children": {
            l2_key: _discovered_l2(
                l2_key,
                f"{name} (General)",
                f"General documents within the discovered category '{name}'.",
            )
        },
    }


def build_final_taxonomy(
    base_tax: Dict[str, dict],
    clusters: List[DiscoveredCluster],
    names: Dict[int, NamingResult],
) -> Dict[str, dict]:
    """Return a new taxonomy = base + grafted discovered nodes.

    ``base_tax`` is the taxonomy this round classified against (the CURRENT
    taxonomy), so a discovered cluster's ``parent_key`` always resolves --
    including parents that are themselves prior-round discovered nodes. Passing
    only the seed skeleton here would drop any cluster discovered under a
    non-seed parent.
    """
    final = copy.deepcopy(base_tax)
    all_keys = _all_keys(final)
    grafted = 0
    for pos, cluster in enumerate(clusters):
        if cluster.unknown or pos not in names:
            continue
        nr = names[pos]
        key = _unique_key(nr.node_key, all_keys)

        if cluster.level == 1 or cluster.parent_key is None:
            # New top-level (L1) category (needs L2+L3 to keep depth 3).
            new_node = _discovered_l1(key, nr.name, nr.desc)
            final[key] = new_node
        else:
            parent = _find_node(final, cluster.parent_key)
            if parent is None:
                log.warning("[emit] parent %r not found for discovered cluster; skipping",
                            cluster.parent_key)
                continue
            children = parent.setdefault("children", {})
            if cluster.level == 2:
                new_node = _discovered_l2(key, nr.name, nr.desc)
            else:  # level == 3
                new_node = _discovered_l3(nr.name, nr.desc)
            children[key] = new_node

        # Register every key the new subtree introduced so later grafts stay unique.
        all_keys.update(_keys_of_subtree(key, new_node))
        grafted += 1

    log.info("[emit] grafted %d discovered node(s) onto the base taxonomy", grafted)
    return final


# ---------------------------------------------------------------------------
# taxonomy.py
# ---------------------------------------------------------------------------


def _render_node(key: str, spec: dict, indent: int) -> List[str]:
    pad = "    " * indent
    lines = [f"{pad}{key!r}: {{"]
    lines.append(f"{pad}    'name': {spec['name']!r},")
    lines.append(f"{pad}    'desc': {spec['desc']!r},")
    lines.append(f"{pad}    'source': {spec.get('source', SEED)!r},")
    children = spec.get("children", {})
    if children:
        lines.append(f"{pad}    'children': {{")
        for ck, cspec in children.items():
            lines.extend(_render_node(ck, cspec, indent + 2))
        lines.append(f"{pad}    }},")
    else:
        lines.append(f"{pad}    'children': {{}},")
    lines.append(f"{pad}}},")
    return lines


def write_taxonomy_py(tax: Dict[str, dict], path: str, meta: dict) -> None:
    """Serialise the merged taxonomy to an importable Python module."""
    header = [
        '"""Final 3-level classification taxonomy produced by the Stage A bootstrap.',
        "",
        "AUTO-GENERATED by kb_classifier/bootstrap/emit.py -- do not edit by",
        "hand; re-run the bootstrap to regenerate. Each node carries source='seed'",
        "(hand-written skeleton) or source='discovered' (added by HDBSCAN gap",
        "discovery and named by the local LLM).",
        "",
    ]
    for k, v in meta.items():
        header.append(f"{k}: {v}")
    header += ['"""', "", "TAXONOMY = {"]

    body: List[str] = []
    for key, spec in tax.items():
        body.extend(_render_node(key, spec, 1))

    footer = ["}", ""]

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(header + body + footer))
    os.replace(tmp, path)
    log.info("[emit] wrote taxonomy -> %s", path)


# ---------------------------------------------------------------------------
# thresholds.json
# ---------------------------------------------------------------------------


def write_thresholds_json(
    results: List[ThresholdResult],
    path: str,
    *,
    n_documents: int,
    embedding_model: str,
    max_seq_length: int,
) -> None:
    by_level = {r.level: r for r in results}
    out = {
        "L1": round(by_level["L1"].value, 6),
        "L2": round(by_level["L2"].value, 6),
        "L3": round(by_level["L3"].value, 6),
        "method_used": {r.level: r.method for r in results},
        "diagnostics": {},
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_documents": n_documents,
        "embedding_model": embedding_model,
        "max_seq_length": max_seq_length,
    }
    for r in results:
        out["diagnostics"][r.level] = {
            "method": r.method,
            "reason": r.reason,
            "n_samples": r.n_samples,
            "gmm_means": list(r.gmm_means) if r.gmm_means else None,
            "gmm_weights": list(r.gmm_weights) if r.gmm_weights else None,
            "gmm_stds": list(r.gmm_stds) if r.gmm_stds else None,
            "separation": r.separation,
            "percentile_used": r.percentile_used,
        }

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    os.replace(tmp, path)
    log.info("[emit] wrote thresholds -> %s", path)
