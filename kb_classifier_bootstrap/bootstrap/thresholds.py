"""Per-level thresholds from the distribution of best-match scores.

Idea (brief, step 2): at each level the per-document best score is bimodal --
documents that genuinely belong to a node score high, documents that don't score
low. Fit a two-component Gaussian mixture to those scores and put the threshold
at the midpoint of the two component means: everything above it is "matched",
everything below goes to the unassigned pool for gap discovery.

The brief says "single-peak -> P30 fallback" but does not define single-peak. We
use two guards (02_DESIGN_NOTES.md A):

  * separation: |mu1 - mu0| divided by the pooled standard deviation. If the two
    components sit almost on top of each other (< min_component_separation),
    there is really one population and the midpoint is meaningless.
  * weight: if either component holds almost nothing (< min_component_weight),
    that "component" is a fitting artefact, not a subpopulation.

Either guard trips the P30 fallback. The final value is clamped to a sane cosine
range so a degenerate fit can't produce an assign-everything or assign-nothing
threshold. Every decision is logged and echoed into thresholds.json diagnostics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from ..config.settings import ThresholdSettings

log = logging.getLogger(__name__)


@dataclass
class ThresholdResult:
    level: str                      # "L1" / "L2" / "L3"
    value: float
    method: str                     # "gmm" | "p30_fallback"
    reason: str
    n_samples: int
    gmm_means: Optional[Tuple[float, float]]
    gmm_weights: Optional[Tuple[float, float]]
    gmm_stds: Optional[Tuple[float, float]]
    separation: Optional[float]
    percentile_used: Optional[float] = None


def _clean_scores(scores: np.ndarray) -> np.ndarray:
    s = np.asarray(scores, dtype=np.float64)
    s = s[np.isfinite(s)]
    return s


def fit_threshold(scores: np.ndarray, level: str, cfg: ThresholdSettings) -> ThresholdResult:
    """Fit a threshold for one level's best-score distribution."""
    s = _clean_scores(scores)
    n = int(s.size)
    log.info("[thresh] %s: %d finite score(s) (min=%.4f, p30=%.4f, median=%.4f, max=%.4f)",
             level, n,
             float(s.min()) if n else float("nan"),
             float(np.percentile(s, 30)) if n else float("nan"),
             float(np.median(s)) if n else float("nan"),
             float(s.max()) if n else float("nan"))

    def clamp(v: float) -> float:
        c = float(min(max(v, cfg.clamp_low), cfg.clamp_high))
        if c != v:
            log.info("[thresh] %s: clamped threshold %.4f -> %.4f into [%.2f, %.2f]",
                     level, v, c, cfg.clamp_low, cfg.clamp_high)
        return c

    # Too few samples to trust a mixture fit -> percentile.
    if n < cfg.min_samples_for_gmm:
        val = float(np.percentile(s, cfg.fallback_percentile)) if n else cfg.clamp_low
        reason = f"only {n} samples (< min_samples_for_gmm={cfg.min_samples_for_gmm})"
        log.info("[thresh] %s: P%.0f fallback -- %s -> threshold=%.4f",
                 level, cfg.fallback_percentile, reason, val)
        return ThresholdResult(level, clamp(val), "p30_fallback", reason, n,
                               None, None, None, None, cfg.fallback_percentile)

    from sklearn.mixture import GaussianMixture

    gmm = GaussianMixture(
        n_components=cfg.gmm_components,
        random_state=cfg.gmm_random_state,
        n_init=cfg.gmm_n_init,
        covariance_type="full",
    )
    gmm.fit(s.reshape(-1, 1))
    means = gmm.means_.ravel()
    weights = gmm.weights_.ravel()
    variances = gmm.covariances_.ravel()
    stds = np.sqrt(np.maximum(variances, 1e-12))

    order = np.argsort(means)          # low component first
    means = means[order]
    weights = weights[order]
    stds = stds[order]

    pooled_std = float(np.sqrt(np.mean(stds ** 2)))
    separation = float(abs(means[1] - means[0]) / max(pooled_std, 1e-9))
    midpoint = float((means[0] + means[1]) / 2.0)

    log.info("[thresh] %s: GMM means=(%.4f, %.4f) weights=(%.3f, %.3f) stds=(%.4f, %.4f) "
             "pooled_std=%.4f separation=%.3f midpoint=%.4f",
             level, means[0], means[1], weights[0], weights[1],
             stds[0], stds[1], pooled_std, separation, midpoint)

    min_weight = float(weights.min())
    gmm_tuple = (float(means[0]), float(means[1]))
    w_tuple = (float(weights[0]), float(weights[1]))
    std_tuple = (float(stds[0]), float(stds[1]))

    if separation < cfg.min_component_separation:
        reason = (f"component separation {separation:.3f} < "
                  f"{cfg.min_component_separation} (unimodal)")
        val = float(np.percentile(s, cfg.fallback_percentile))
        log.info("[thresh] %s: P%.0f fallback -- %s -> threshold=%.4f",
                 level, cfg.fallback_percentile, reason, val)
        return ThresholdResult(level, clamp(val), "p30_fallback", reason, n,
                               gmm_tuple, w_tuple, std_tuple, separation,
                               cfg.fallback_percentile)

    if min_weight < cfg.min_component_weight:
        reason = (f"smallest component weight {min_weight:.3f} < "
                  f"{cfg.min_component_weight} (fitting artefact)")
        val = float(np.percentile(s, cfg.fallback_percentile))
        log.info("[thresh] %s: P%.0f fallback -- %s -> threshold=%.4f",
                 level, cfg.fallback_percentile, reason, val)
        return ThresholdResult(level, clamp(val), "p30_fallback", reason, n,
                               gmm_tuple, w_tuple, std_tuple, separation,
                               cfg.fallback_percentile)

    reason = "two well-separated components; threshold = midpoint of means"
    log.info("[thresh] %s: GMM accepted -- %s -> threshold=%.4f", level, reason, midpoint)
    return ThresholdResult(level, clamp(midpoint), "gmm", reason, n,
                           gmm_tuple, w_tuple, std_tuple, separation, None)
