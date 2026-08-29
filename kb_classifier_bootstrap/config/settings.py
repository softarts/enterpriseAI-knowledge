"""Central hyperparameters for the Bootstrap (Stage A) run.

Everything tunable lives here so that ``bootstrap_report.md`` can quote the
exact settings a given taxonomy was produced under. ``describe()`` renders the
whole config as log lines; the orchestrator prints it at startup so any run is
reproducible from its own log.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

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
    # discovery.choose_min_cluster_size) so that a 40k-document pool does not
    # get shattered into hundreds of 5-document nodes.
    base_min_cluster_size: int = 5
    min_cluster_size_pool_fraction: float = 0.01   # 1% of pool
    max_min_cluster_size: int = 400

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
    """Local Ollama LLM naming of discovered clusters."""

    ollama_host: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    # Primary choice per the brief: code-specialised but built on the Qwen2.5
    # base, so general language ability is intact and the extra parameters beat
    # a 3B general model at "read five titles, emit a category name".
    primary_model: str = "qwen2.5-coder:7b"
    comparison_model: str = "qwen2.5:3b"

    # One-off model-selection experiment: run BOTH models on this many
    # clusters, log both outputs side by side, then use primary_model for
    # everything. This is model selection, not human-in-the-loop
    # classification.
    comparison_cluster_count: int = 4

    temperature: float = 0.1
    num_predict: int = 200
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
        return os.path.join(self.package_root, "bootstrap_report.md")


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
