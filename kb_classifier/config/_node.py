"""Shared node constructor for the hand-written taxonomy skeleton.

Every taxonomy node has the same shape regardless of level:

    {
        "name":     human-readable display name,
        "desc":     one-sentence *semantic* description (this is the text that
                    gets embedded by bge-m3 and compared against documents, so
                    it deliberately spells out the vocabulary you would expect
                    in a matching article rather than restating the name),
        "source":   "seed" for hand-written anchors, "discovered" for nodes
                    appended by the HDBSCAN gap-discovery step,
        "children": dict of child nodes (empty at L3),
    }
"""

from __future__ import annotations

from typing import Any, Dict

SEED = "seed"
DISCOVERED = "discovered"


def node(name: str, desc: str, children: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Build a hand-written ("seed") taxonomy node."""
    return {
        "name": name,
        "desc": desc,
        "source": SEED,
        "children": children if children is not None else {},
    }
