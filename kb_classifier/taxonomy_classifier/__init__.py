"""Taxonomy classifier: per-article, rule-based classification at import time.

This is the steady-state, production API (formerly ``stage_b``). It consumes
the frozen Stage A artifacts (a pinned ``taxonomy_v<N>.py`` + ``thresholds.json``)
read-only and assigns each document a three-level taxonomy path via the same
hierarchical nearest-anchor matching used in bootstrap. No clustering and no LLM
calls -- each document is a handful of dot products, so it is cheap enough to run
inline when a single document (or a batch) is imported.

Typical use::

    from kb_classifier.taxonomy_classifier.classify import TaxonomyClassifier

    clf = TaxonomyClassifier()               # loads the pinned frozen taxonomy
    result = clf.classify_text(title, body)  # -> Classification
    metadata = result.to_okf_metadata(doc_id=doc_id)

``Classifier`` remains available as a backwards-compatible alias for
``TaxonomyClassifier``.
"""

from typing import TYPE_CHECKING

__all__ = ["Classification", "Classifier", "TaxonomyClassifier"]

if TYPE_CHECKING:  # for type checkers / IDEs only
    from .classify import Classification, Classifier, TaxonomyClassifier


def __getattr__(name: str):
    """Lazily re-export from .classify.

    Kept lazy (PEP 562) so that ``python -m kb_classifier.taxonomy_classifier.classify``
    does not import the submodule twice (which triggers a runpy RuntimeWarning),
    while ``from kb_classifier.taxonomy_classifier import TaxonomyClassifier`` still works.
    """
    if name in __all__:
        from . import classify
        return getattr(classify, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
