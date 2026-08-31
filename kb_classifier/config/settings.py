"""Central hyperparameters for the Bootstrap (Stage A) run.

Everything tunable lives here so that ``bootstrap_report.md`` can quote the
exact settings a given taxonomy was produced under. ``describe()`` renders the
whole config as log lines; the orchestrator prints it at startup so any run is
reproducible from its own log.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_PKG_ROOT)


@dataclass(frozen=True)
class EmbeddingSettings:
    """bge-m3 embedding of documents and taxonomy anchors."""

    model_name: str = "BAAI/bge-m3"

    # bge-m3 advertises max_seq_length 8192, but we deliberately truncate hard.
    # Rationale: (a) attention cost is superlinear in sequence length and the
    # bootstrap corpus is ~512k documents, (b) for *topical* classification the
    # title plus opening paragraphs carry nearly all the signal -- the tail of a
    # runbook or email thread is mostly procedural detail that blurs the topic
    # centroid. 512 tokens is the standard retrieval-model operating point and
    # keeps the whole run tractable on a 4 GB GPU.
    max_seq_length: int = 512

    # Characters of body text kept before tokenisation. ~4 chars/token for
    # English, so 2000 chars comfortably saturates a 512-token budget while
    # avoiding tokenising megabytes we would immediately discard.
    body_char_budget: int = 2000

    # Title is repeated once ahead of the body: it is the single most
    # discriminative field and this cheaply up-weights it without a custom
    # pooling layer.
    repeat_title: bool = True

    batch_size: int = 8          # tuned for 4 GB VRAM at 512 tokens
    use_fp16: bool = True
    device: str = "auto"         # "auto" -> cuda if available else cpu

    # Documents per checkpoint shard. Smaller = less lost work on interrupt,
    # more files. 2000 x 1024 x fp16 = ~4 MB per shard.
    shard_size: int = 2000


@dataclass(frozen=True)
class MatchingSettings:
    """Level-by-level anchor matching."""

    # Anchor text fed to bge-m3 is "<breadcrumb>: <desc>". Including the parent
    # breadcrumb disambiguates sibling nodes that share vocabulary (e.g.
    # Treasury > Cash Management vs Corporate Banking > Cash Management
    # Services), which pure-desc anchors handle poorly.
    include_breadcrumb: bool = True


@dataclass(frozen=True)
class ThresholdSettings:
    """Per-level threshold derivation from the top-score distribution."""

    # Two-component GMM on the per-level best-match scores; threshold is the
    # midpoint of the two component means.
    gmm_components: int = 2
    gmm_random_state: int = 42
    gmm_n_init: int = 5

    # Unimodality guard. If the fitted components are not meaningfully
    # separated the "two populations" story does not hold, so we fall back to a
    # percentile. Separation is measured as |mu1 - mu0| in units of pooled
    # standard deviation.
    min_component_separation: float = 1.0

    # A component holding almost nothing is a fitting artefact, not a
    # population: also triggers the fallback.
    min_component_weight: float = 0.05

    fallback_percentile: float = 30.0     # P30, per the brief
    min_samples_for_gmm: int = 50

    # Absolute sanity clamp on cosine similarity thresholds. Prevents a
    # degenerate fit from producing a threshold that assigns everything or
    # nothing.
    clamp_low: float = 0.15
    clamp_high: float = 0.80


@dataclass(frozen=True)
class DiscoverySettings:
    """HDBSCAN gap discovery over per-parent unassigned pools."""

    # Pools smaller than this are not clustered at all; their documents are
    # marked UNKNOWN. Below ~5 documents a "cluster" is noise, and naming it
    # would pollute the taxonomy with one-off nodes.
    min_pool_size: int = 5

    # HDBSCAN min_cluster_size. Scaled with pool size (see
    # discovery.choose_min_cluster_size).
    #
    # These values were re-tuned after the v2 (23k-doc) run, where the old
    # settings (floor 5, fraction 0.01, cap 400) drove the 11.6k-document L1
    # UNKNOWN pool to min_cluster_size=116 and HDBSCAN(eom) returned ZERO
    # clusters (100% noise). An mcs sweep on that exact pool showed clusters
    # only appear for mcs in ~[15, 45]; at mcs>=50 everything collapses to
    # noise. The 1% fraction was hitting that dead zone as soon as a pool passed
    # ~4,500 documents.
    #
    # New scaling: max(15, min(0.003 * pool, 50)).
    #   - floor 15  : matches the v1 L1 pool (1,552 -> 15) that discovered fine;
    #                 also stops tiny pools shattering into micro-clusters.
    #   - 0.3%      : keeps mcs inside the productive band far longer
    #                 (11,641 -> 34, still in [15,45]).
    #   - cap 50    : an upper bound just below the empirical collapse point,
    #                 so even very large pools stay clusterable.
    # See choose_min_cluster_size: the fraction is applied to the *effective*
    # clustering size (pool capped at max_pool_for_clustering), because pools
    # larger than that are sub-sampled before HDBSCAN sees them.
    base_min_cluster_size: int = 15
    min_cluster_size_pool_fraction: float = 0.003
    max_min_cluster_size: int = 50

    metric: str = "euclidean"   # on L2-normalised vectors this is monotone in
                                # cosine distance, and is the fast code path
    cluster_selection_method: str = "eom"

    # Cap on new nodes appended under any single parent, to keep the emitted
    # taxonomy human-readable. Largest clusters win.
    max_new_nodes_per_parent: int = 8

    # Representative documents per cluster fed to the naming model.
    representatives_per_cluster: int = 5
    representative_body_chars: int = 100

    # HDBSCAN is O(n log n)-ish but memory-hungry; subsample very large pools
    # for the clustering step, then assign the remainder to the nearest
    # discovered centroid.
    max_pool_for_clustering: int = 20000


@dataclass(frozen=True)
class NamingSettings:
    """Local LLM naming of discovered clusters.

    Naming uses a single local generation model, ``qwen3-8b-mlx``, served by
    **LM Studio** over an *OpenAI-compatible* API (``/v1/chat/completions``).
    Everything is fully local; no cloud LLM is called.
    """

    # OpenAI-compatible base URL (LM Studio default port 1234).
    api_base: str = os.environ.get("LMSTUDIO_API_BASE", "http://localhost:1234/v1")
    api_key: str = os.environ.get("LMSTUDIO_API_KEY", "lm-studio")  # LM Studio ignores it

    # The single generation model loaded in LM Studio.
    primary_model: str = "qwen3-8b-mlx"

    # qwen3-8b-mlx is a *reasoning* model: left to itself it spends the token
    # budget on a hidden chain-of-thought and can return empty content when the
    # budget runs out. For "read five titles, emit a category name" reasoning
    # adds only latency and truncation risk, so we suppress it with Qwen3's
    # ``/no_think`` control token in the system prompt. chat_template_kwargs
    # {"enable_thinking": false} was tested against this LM Studio build and did
    # NOT take effect, so /no_think is the reliable lever.
    disable_thinking: bool = True

    temperature: float = 0.1
    # Generous ceiling: even with /no_think we leave headroom so a stray
    # thinking token can never truncate the JSON answer.
    max_tokens: int = 512
    request_timeout_s: int = 180
    max_retries: int = 2


@dataclass(frozen=True)
class CorpusSettings:
    """Where the bootstrap articles come from and how many are used."""

    root: str = os.path.join(_REPO_ROOT, "all_documents")
    extensions: tuple = (".txt",)
    min_file_bytes: int = 200      # skip stubs with no usable body

    # None => use every document found (true full scan).
    max_docs: int | None = None

    # Proportional-with-floor stratified sampling when max_docs is set.
    # Stratum = "<source>/<subdir>" (e.g. "slack/eng-ml"), so every channel,
    # mailbox and space keeps representation instead of slack+gmail (80% of the
    # corpus by count) crowding everything else out.
    stratify: bool = True
    stratum_depth: int = 2
    min_per_stratum: int = 3
    sampling_seed: int = 20260829


@dataclass(frozen=True)
class Paths:
    package_root: str = _PKG_ROOT
    config_dir: str = _HERE
    work_dir: str = os.path.join(_PKG_ROOT, "work")

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.work_dir, "manifest.jsonl")

    @property
    def embed_dir(self) -> str:
        return os.path.join(self.work_dir, "embeddings")

    @property
    def embed_state_path(self) -> str:
        return os.path.join(self.embed_dir, "state.json")

    @property
    def vector_store_path(self) -> str:
        # Content-addressed embedding cache (SQLite), shared across manifests.
        return os.path.join(self.work_dir, "vector_store.sqlite")

    @property
    def anchor_cache_path(self) -> str:
        return os.path.join(self.work_dir, "anchor_embeddings.npz")

    @property
    def match_result_path(self) -> str:
        return os.path.join(self.work_dir, "match_results.npz")

    @property
    def naming_cache_path(self) -> str:
        return os.path.join(self.work_dir, "naming_cache.json")

    @property
    def run_log_path(self) -> str:
        return os.path.join(self.work_dir, "bootstrap_run.log")

    @property
    def taxonomy_out_path(self) -> str:
        return os.path.join(self.config_dir, "taxonomy.py")

    @property
    def thresholds_out_path(self) -> str:
        return os.path.join(self.config_dir, "thresholds.json")

    @property
    def report_out_path(self) -> str:
        # Base name only; the actual per-run file is versioned. See
        # versioned_report_path(). Kept for reference/back-compat.
        return os.path.join(self.package_root, "bootstrap_report.md")

    # ---- versioned discovery-loop artifacts ---------------------------------
    #
    # Each discovery round produces three artifacts that MUST share the same
    # version number N so they can be cross-referenced:
    #   config/taxonomy_v<N>.py          (the complete taxonomy that round built)
    #   bootstrap_report_v<N>_<stamp>.md (its report)
    #   work/snapshot_v<N>.json          (machine-readable snapshot for diffs)
    # In addition config/taxonomy.py always mirrors the latest taxonomy_v<N>.py.
    #
    # N is derived from the HIGHEST version already present across all three
    # artifact families, so a run is robust to any one of them being missing
    # (e.g. legacy runs wrote reports/snapshots but no taxonomy_v<N>.py yet).

    @staticmethod
    def sample_count_label(n_docs: int) -> str:
        """Human-friendly document-count tag for versioned filenames.

        Derived from the round's ACTUAL document count, never hard-coded:
          3000 -> "3k", 23000 -> "23k", 100000 -> "100k", 800 -> "800".
        Values >= 1000 that divide evenly render as "<k>k"; otherwise a one-
        decimal "k" (e.g. 1500 -> "1.5k"); values < 1000 render as the integer.
        """
        if n_docs >= 1000:
            k = n_docs / 1000.0
            if abs(k - round(k)) < 1e-9:
                return f"{int(round(k))}k"
            return f"{k:.1f}k"
        return str(int(n_docs))

    def _highest_existing_version(self) -> int:
        import glob
        import re

        highest = 0
        # Regexes tolerate BOTH the legacy pattern (taxonomy_v3.py) and the
        # sample-count pattern (taxonomy_v4_100k.py), so version detection keeps
        # working across the rename.
        families = (
            (self.config_dir, r"taxonomy_v(\d+)(?:_[^.]+)?\.py$"),
            (self.package_root, r"bootstrap_report_v(\d+)_"),
            (self.work_dir, r"snapshot_v(\d+)(?:_[^.]+)?\.json$"),
        )
        for directory, pat in families:
            rx = re.compile(pat)
            for p in glob.glob(os.path.join(directory, "*")):
                m = rx.search(os.path.basename(p))
                if m:
                    highest = max(highest, int(m.group(1)))
        # A legacy bare bootstrap_report.md counts as v1 if nothing else exists.
        if highest == 0 and os.path.exists(self.report_out_path):
            highest = 1
        return highest

    def next_version(self) -> int:
        """The version number this round should use (highest existing + 1)."""
        return self._highest_existing_version() + 1

    def previous_version(self, current: int) -> int:
        """Highest version strictly below ``current`` that has a snapshot, else 0."""
        import glob
        import re

        # Match legacy (snapshot_v3.json) and sample-count (snapshot_v4_100k.json).
        rx = re.compile(r"snapshot_v(\d+)(?:_[^.]+)?\.json$")
        best = 0
        for p in glob.glob(os.path.join(self.work_dir, "snapshot_v*.json")):
            m = rx.search(os.path.basename(p))
            if m:
                v = int(m.group(1))
                if v < current:
                    best = max(best, v)
        return best

    @staticmethod
    def _version_suffix(count_label: Optional[str]) -> str:
        return f"_{count_label}" if count_label else ""

    def taxonomy_version_path(self, version: int, count_label: Optional[str] = None) -> str:
        """Per-round taxonomy file, e.g. taxonomy_v3_100k.py.

        ``count_label`` comes from sample_count_label(n_docs). Omitting it yields
        the legacy taxonomy_v<N>.py form (kept for back-compat / discovery).
        """
        return os.path.join(
            self.config_dir,
            f"taxonomy_v{version}{self._version_suffix(count_label)}.py",
        )

    def snapshot_path(self, version: int, count_label: Optional[str] = None) -> str:
        return os.path.join(
            self.work_dir,
            f"snapshot_v{version}{self._version_suffix(count_label)}.json",
        )

    def find_snapshot_for_version(self, version: int) -> Optional[str]:
        """Locate an existing snapshot for ``version`` regardless of its count
        label (snapshot_v3.json or snapshot_v3_23k.json). Returns the path or
        None. Used for the prev->current report diff, where the previous round's
        document count is not known here.
        """
        import glob

        matches = glob.glob(os.path.join(self.work_dir, f"snapshot_v{version}.json"))
        matches += glob.glob(os.path.join(self.work_dir, f"snapshot_v{version}_*.json"))
        return matches[0] if matches else None

    def report_path_for_version(self, version: int, count_label: Optional[str] = None) -> str:
        import time

        stamp = time.strftime("%Y%m%d-%H%M")
        return os.path.join(
            self.package_root,
            f"bootstrap_report_v{version}{self._version_suffix(count_label)}_{stamp}.md",
        )

    def versioned_report_path(self) -> str:
        """Back-compat: next versioned report path for the shared N.

        Kept for callers that only want the report path; prefer computing N once
        via next_version() and using report_path_for_version(N) so the taxonomy,
        report and snapshot all share the same N.
        """
        return self.report_path_for_version(self.next_version())


@dataclass(frozen=True)
class Settings:
    corpus: CorpusSettings = field(default_factory=CorpusSettings)
    embedding: EmbeddingSettings = field(default_factory=EmbeddingSettings)
    matching: MatchingSettings = field(default_factory=MatchingSettings)
    thresholds: ThresholdSettings = field(default_factory=ThresholdSettings)
    discovery: DiscoverySettings = field(default_factory=DiscoverySettings)
    naming: NamingSettings = field(default_factory=NamingSettings)
    paths: Paths = field(default_factory=Paths)

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("paths", None)
        return d

    def describe(self) -> List[str]:
        """Flat, greppable log lines for every hyperparameter."""
        lines: List[str] = []
        for section, values in self.as_dict().items():
            for key, value in values.items():
                lines.append(f"  cfg.{section}.{key} = {value!r}")
        return lines

    def embedding_fingerprint(self) -> Dict[str, Any]:
        """Settings that invalidate an existing embedding cache if changed."""
        e = self.embedding
        return {
            "model_name": e.model_name,
            "max_seq_length": e.max_seq_length,
            "body_char_budget": e.body_char_budget,
            "repeat_title": e.repeat_title,
            "use_fp16": e.use_fp16,
            "shard_size": e.shard_size,
        }


SETTINGS = Settings()
