"""Stand-alone, resumable embedding stage.

This is deliberately a separate entry point from run_bootstrap.py: embedding is
the only expensive stage, and on a 4 GB GPU over ~512k documents it is a
long-running job that you will want to start, stop and resume independently of
the cheap downstream stages.

Typical use
-----------
  # 1. Freeze the document manifest (full corpus)
  python -m kb_classifier_bootstrap.run_embed manifest

  # ... or a stratified sample
  python -m kb_classifier_bootstrap.run_embed manifest --max-docs 30000

  # 2. Measure throughput on this machine before committing to a full pass
  python -m kb_classifier_bootstrap.run_embed benchmark --shards 3

  # 3. Embed. Ctrl-C at any time; re-run the same command to continue.
  python -m kb_classifier_bootstrap.run_embed embed
  python -m kb_classifier_bootstrap.run_embed embed --time-budget-min 90

  # 4. Check where you are without loading the model
  python -m kb_classifier_bootstrap.run_embed status
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import sys
import time
from typing import List, Optional

from .bootstrap.corpus import (
    build_manifest,
    load_manifest,
    manifest_fingerprint,
)
from .bootstrap.embedder import (
    BgeM3Embedder,
    CacheStateError,
    embed_corpus_resumable,
    existing_shard_starts,
    plan_shards,
    read_cached_shard_size,
)
from .config.settings import SETTINGS, Settings

log = logging.getLogger("kb_bootstrap.embed")


_NOISY_LOGGERS = (
    "sentence_transformers",
    "transformers",
    "httpx",
    "httpcore",
    "urllib3",
    "filelock",
    "huggingface_hub",
    "PIL",
    "matplotlib",
)


def setup_logging(log_path: Optional[str], verbose: bool = False) -> None:
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_path:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )
    # These emit per-request DEBUG lines that bury the progress log.
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def _settings_with_overrides(args: argparse.Namespace) -> Settings:
    s = SETTINGS
    corpus = s.corpus
    if getattr(args, "max_docs", None) is not None:
        corpus = dataclasses.replace(corpus, max_docs=args.max_docs)
    if getattr(args, "no_stratify", False):
        corpus = dataclasses.replace(corpus, stratify=False)
    embedding = s.embedding
    if getattr(args, "batch_size", None):
        embedding = dataclasses.replace(embedding, batch_size=args.batch_size)
    if getattr(args, "shard_size", None):
        embedding = dataclasses.replace(embedding, shard_size=args.shard_size)
    if getattr(args, "device", None):
        embedding = dataclasses.replace(embedding, device=args.device)
    return dataclasses.replace(s, corpus=corpus, embedding=embedding)


def _adopt_cached_shard_size(cfg: Settings, explicit: Optional[int]) -> Settings:
    """Make an existing cache's shard_size authoritative.

    Counting shards with the wrong shard_size silently misreports progress (and
    can declare a partial cache COMPLETE), so the value stored alongside the
    cache always wins over a CLI default. An explicit --shard-size that
    disagrees is a real conflict and is surfaced loudly.
    """
    cached = read_cached_shard_size(cfg.paths.embed_state_path)
    if cached is None or cached == cfg.embedding.shard_size:
        return cfg
    if explicit is not None:
        log.warning(
            "[embed] --shard-size %d conflicts with the existing cache "
            "(built with shard_size=%d). Using the cached value; delete %s if "
            "you really want to re-shard.",
            explicit,
            cached,
            cfg.paths.embed_dir,
        )
    else:
        log.info("[embed] adopting shard_size=%d from the existing cache", cached)
    return dataclasses.replace(
        cfg, embedding=dataclasses.replace(cfg.embedding, shard_size=cached)
    )


# ---------------------------------------------------------------------------
# subcommands
# ---------------------------------------------------------------------------


def cmd_manifest(args: argparse.Namespace) -> int:
    cfg = _settings_with_overrides(args)
    setup_logging(cfg.paths.run_log_path)
    log.info("=" * 78)
    log.info("STAGE: build document manifest")
    log.info("=" * 78)
    for line in cfg.describe():
        log.info(line)

    path = cfg.paths.manifest_path
    if os.path.exists(path) and not args.force:
        entries = load_manifest(path)
        log.warning(
            "[manifest] %s already exists with %d rows. Refusing to overwrite: "
            "rebuilding it would invalidate every embedding shard. Pass --force "
            "if that is what you want.",
            path,
            len(entries),
        )
        return 1

    if os.path.exists(path) and args.force:
        shards = existing_shard_starts(cfg.paths.embed_dir)
        if shards:
            log.warning(
                "[manifest] --force with %d existing embedding shard(s). Those "
                "shards will become unusable (manifest fingerprint changes) and "
                "the next embed run will refuse to resume. Delete %s to start "
                "clean.",
                len(shards),
                cfg.paths.embed_dir,
            )

    entries = build_manifest(cfg.corpus, path)
    log.info("[manifest] fingerprint = %s", manifest_fingerprint(entries))
    log.info(
        "[manifest] planned shards: %d at shard_size=%d",
        len(plan_shards(len(entries), cfg.embedding.shard_size)),
        cfg.embedding.shard_size,
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = _settings_with_overrides(args)
    setup_logging(None)
    cfg = _adopt_cached_shard_size(cfg, args.shard_size)
    path = cfg.paths.manifest_path
    if not os.path.exists(path):
        log.error("[status] no manifest at %s -- run the 'manifest' command first", path)
        return 1
    entries = load_manifest(path)
    shards = plan_shards(len(entries), cfg.embedding.shard_size)
    have = existing_shard_starts(cfg.paths.embed_dir)
    expected = {s.start: s.count for s in shards}
    stray = sorted(s for s in have if s not in expected)
    if stray:
        log.warning(
            "[status] %d shard file(s) do not match the current shard plan "
            "(first at row %d) -- they are stale and will be ignored: %s",
            len(stray),
            stray[0],
            stray[:5],
        )
    done_docs = sum(expected[s] for s in have if s in expected)
    pct = 100.0 * done_docs / max(len(entries), 1)
    log.info("manifest            : %s", path)
    log.info("manifest documents  : %d", len(entries))
    log.info("manifest fingerprint: %s", manifest_fingerprint(entries))
    log.info("shard size          : %d", cfg.embedding.shard_size)
    log.info("shards complete     : %d / %d", len(have), len(shards))
    log.info("documents embedded  : %d / %d  (%.2f%%)", done_docs, len(entries), pct)
    log.info("embeddings dir      : %s", cfg.paths.embed_dir)
    missing = [s.start for s in shards if s.start not in have]
    if missing:
        log.info("next missing shard  : row %d", missing[0])
        log.info("remaining documents : %d", len(entries) - done_docs)
        log.info("STATUS              : INCOMPLETE (%d shard(s) to go)", len(missing))
        return 3
    log.info("STATUS              : COMPLETE")
    return 0


def _run_embed(cfg: Settings, *, max_new_shards, time_budget_s) -> int:
    path = cfg.paths.manifest_path
    if not os.path.exists(path):
        log.error("[embed] no manifest at %s -- run the 'manifest' command first", path)
        return 1
    entries = load_manifest(path)
    fp = manifest_fingerprint(entries)
    log.info("[embed] manifest: %d documents, fingerprint=%s", len(entries), fp)

    embedder = BgeM3Embedder(cfg.embedding)
    try:
        progress = embed_corpus_resumable(
            embedder=embedder,
            corpus_root=cfg.corpus.root,
            entries=entries,
            embed_dir=cfg.paths.embed_dir,
            state_path=cfg.paths.embed_state_path,
            embed_fingerprint=cfg.embedding_fingerprint(),
            manifest_fingerprint=fp,
            shard_size=cfg.embedding.shard_size,
            max_new_shards=max_new_shards,
            time_budget_s=time_budget_s,
        )
    except CacheStateError as exc:
        log.error("[embed] %s", exc)
        return 2
    except KeyboardInterrupt:
        log.warning(
            "[embed] interrupted by user. Completed shards are safe on disk; "
            "re-run the same command to resume."
        )
        return 130

    if progress.complete:
        log.info("[embed] EMBEDDING COMPLETE for all %d documents", progress.total_docs)
    else:
        remaining = progress.total_docs - (progress.already_done + progress.newly_done)
        eta_min = (
            remaining / progress.docs_per_s / 60.0 if progress.docs_per_s > 0 else float("nan")
        )
        log.info(
            "[embed] stopped early: %d document(s) remain (~%.1f min at %.1f docs/s). "
            "Re-run to continue.",
            remaining,
            eta_min,
            progress.docs_per_s,
        )
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    cfg = _settings_with_overrides(args)
    setup_logging(cfg.paths.run_log_path)
    log.info("=" * 78)
    log.info("STAGE: embed documents (resumable)")
    log.info("=" * 78)
    cfg = _adopt_cached_shard_size(cfg, args.shard_size)
    time_budget_s = args.time_budget_min * 60.0 if args.time_budget_min else None
    return _run_embed(cfg, max_new_shards=args.max_shards, time_budget_s=time_budget_s)


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Measure real throughput, then extrapolate to the full manifest.

    Written as its own command because guessing at bge-m3 throughput on an
    unfamiliar GPU is exactly the kind of estimate that is wrong by 5x.
    """
    cfg = _settings_with_overrides(args)
    setup_logging(cfg.paths.run_log_path)
    log.info("=" * 78)
    log.info("STAGE: embedding throughput benchmark")
    log.info("=" * 78)

    cfg = _adopt_cached_shard_size(cfg, args.shard_size)
    path = cfg.paths.manifest_path
    if not os.path.exists(path):
        log.error("[bench] no manifest at %s -- run the 'manifest' command first", path)
        return 1
    entries = load_manifest(path)

    t0 = time.time()
    rc = _run_embed(cfg, max_new_shards=args.shards, time_budget_s=None)
    if rc != 0:
        return rc
    elapsed = time.time() - t0

    have = existing_shard_starts(cfg.paths.embed_dir)
    done_docs = sum(
        min(cfg.embedding.shard_size, len(entries) - s) for s in have if s < len(entries)
    )
    embedded_now = args.shards * cfg.embedding.shard_size
    embedded_now = min(embedded_now, len(entries))
    rate = embedded_now / max(elapsed, 1e-6)

    log.info("-" * 78)
    log.info("BENCHMARK RESULT")
    log.info("  documents embedded this run : %d", embedded_now)
    log.info("  wall clock                  : %.1f s", elapsed)
    log.info("  throughput                  : %.2f docs/s", rate)
    log.info("  batch_size / max_seq_length : %d / %d",
             cfg.embedding.batch_size, cfg.embedding.max_seq_length)
    log.info("  cache now holds             : %d / %d documents", done_docs, len(entries))
    for label, n in (
        ("current manifest", len(entries)),
        ("30,000 sample", 30_000),
        ("50,000 sample", 50_000),
        ("full 511,963 corpus", 511_963),
    ):
        if rate > 0:
            hours = n / rate / 3600.0
            log.info("  projected time for %-20s (%7d docs): %6.2f h", label, n, hours)
    log.info("-" * 78)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m kb_classifier_bootstrap.run_embed",
        description="Resumable bge-m3 embedding stage for the KB bootstrap.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--shard-size", type=int, default=None,
                        help="documents per checkpoint shard")
        sp.add_argument("--batch-size", type=int, default=None,
                        help="encoder batch size (lower this if you hit OOM)")
        sp.add_argument("--device", default=None, choices=["auto", "cuda", "cpu"])

    sp = sub.add_parser("manifest", help="scan the corpus and freeze the document manifest")
    sp.add_argument("--max-docs", type=int, default=None,
                    help="cap document count (omit for a true full scan)")
    sp.add_argument("--no-stratify", action="store_true",
                    help="uniform random sample instead of stratified")
    sp.add_argument("--force", action="store_true",
                    help="overwrite an existing manifest (invalidates embedding shards)")
    add_common(sp)
    sp.set_defaults(func=cmd_manifest)

    sp = sub.add_parser("status", help="report embedding progress without loading the model")
    add_common(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("embed", help="embed remaining documents (safe to interrupt and re-run)")
    sp.add_argument("--max-shards", type=int, default=None,
                    help="stop after writing this many new shards")
    sp.add_argument("--time-budget-min", type=float, default=None,
                    help="stop after roughly this many minutes")
    add_common(sp)
    sp.set_defaults(func=cmd_embed)

    sp = sub.add_parser("benchmark", help="measure docs/s and project full-run time")
    sp.add_argument("--shards", type=int, default=2,
                    help="number of shards to embed for the measurement")
    add_common(sp)
    sp.set_defaults(func=cmd_benchmark)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
