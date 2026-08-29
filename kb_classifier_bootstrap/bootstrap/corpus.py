"""Corpus discovery, document parsing, and the frozen document manifest.

The manifest is the backbone of resumability. It is built once, written to
``work/manifest.jsonl``, and thereafter treated as immutable: document ``i`` is
always the same article, so an embedding shard covering rows [2000, 4000) stays
valid across restarts.

Corpus format (verified by scan_corpus.py against all 9 source trees): every
document is a UTF-8 ``.txt`` file whose first non-empty line is the title and
whose remainder is the body.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterator, List, Sequence

from ..config.settings import CorpusSettings

log = logging.getLogger(__name__)


@dataclass
class Document:
    doc_index: int      # position in the frozen manifest
    doc_id: str         # stable id derived from the relative path
    rel_path: str
    stratum: str        # e.g. "slack/eng-ml"
    source: str         # e.g. "slack"
    title: str
    body: str

    def embed_text(self, body_char_budget: int, repeat_title: bool) -> str:
        """Build the text handed to bge-m3."""
        body = self.body[:body_char_budget]
        if repeat_title and self.title:
            return f"{self.title}\n{self.title}\n{body}"
        return f"{self.title}\n{body}"


@dataclass
class ManifestEntry:
    doc_index: int
    doc_id: str
    rel_path: str
    stratum: str
    source: str
    title: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "doc_index": self.doc_index,
                "doc_id": self.doc_id,
                "rel_path": self.rel_path,
                "stratum": self.stratum,
                "source": self.source,
                "title": self.title,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def from_json(line: str) -> "ManifestEntry":
        d = json.loads(line)
        return ManifestEntry(
            doc_index=d["doc_index"],
            doc_id=d["doc_id"],
            rel_path=d["rel_path"],
            stratum=d["stratum"],
            source=d["source"],
            title=d["title"],
        )


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


def _derive_doc_id(rel_path: str) -> str:
    """Stable, filesystem-independent id.

    Filenames already embed a ``dsid_<hex>`` document id in this corpus; we keep
    it when present (it is the upstream identity and lets us cross-reference the
    OKF pipeline) and otherwise hash the path.
    """
    base = os.path.basename(rel_path)
    if base.startswith("dsid_"):
        tail = base[len("dsid_"):]
        hexpart = tail.split("__", 1)[0]
        if len(hexpart) == 32 and all(c in "0123456789abcdef" for c in hexpart):
            return f"dsid_{hexpart}"
    digest = hashlib.sha1(rel_path.replace("\\", "/").encode("utf-8")).hexdigest()
    return f"path_{digest[:24]}"


def _stratum_of(rel_path: str, depth: int) -> tuple[str, str]:
    parts = rel_path.replace("\\", "/").split("/")
    source = parts[0] if parts else "unknown"
    # Drop the filename before taking the directory prefix.
    dirs = parts[:-1] or [source]
    stratum = "/".join(dirs[:depth]) if dirs else source
    return stratum, source


def parse_document_text(raw: str) -> tuple[str, str]:
    """Split raw file content into (title, body).

    Title is the first non-empty line. Some google_drive exports contain literal
    ``\\n`` two-character sequences instead of real newlines; those are
    normalised so the body reads as prose to the encoder.
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    title = ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip():
            title = line.strip()
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:]).strip()
    if "\\n" in body:
        body = body.replace("\\n", "\n")
    return title, body


def read_document(root: str, entry: ManifestEntry) -> Document:
    full = os.path.join(root, entry.rel_path)
    with open(full, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    title, body = parse_document_text(raw)
    return Document(
        doc_index=entry.doc_index,
        doc_id=entry.doc_id,
        rel_path=entry.rel_path,
        stratum=entry.stratum,
        source=entry.source,
        title=title or entry.title,
        body=body,
    )


# ---------------------------------------------------------------------------
# manifest construction
# ---------------------------------------------------------------------------


def _scan_candidates(cfg: CorpusSettings) -> List[tuple[str, str, str]]:
    """Walk the corpus root, returning sorted (rel_path, stratum, source)."""
    out: List[tuple[str, str, str]] = []
    exts = tuple(e.lower() for e in cfg.extensions)
    for dirpath, dirnames, filenames in os.walk(cfg.root):
        dirnames.sort()
        for fn in sorted(filenames):
            if not fn.lower().endswith(exts):
                continue
            full = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(full) < cfg.min_file_bytes:
                    continue
            except OSError:
                continue
            rel = os.path.relpath(full, cfg.root).replace("\\", "/")
            if "/" not in rel:
                # Loose files at the corpus root (e.g. questions.jsonl siblings)
                # have no stratum; skip rather than invent one.
                continue
            stratum, source = _stratum_of(rel, cfg.stratum_depth)
            out.append((rel, stratum, source))
    # Deterministic global order -> stable doc_index across runs.
    out.sort(key=lambda t: t[0])
    return out


def stratified_sample(
    candidates: Sequence[tuple[str, str, str]],
    max_docs: int,
    min_per_stratum: int,
    seed: int,
) -> List[tuple[str, str, str]]:
    """Proportional-with-floor stratified sample.

    Without a floor, strata holding <0.01% of the corpus would draw zero
    documents and their topics would be invisible to gap discovery. Without
    proportionality, slack (56% of the corpus) would be no better represented
    than a 40-document folder. So: give every stratum ``min_per_stratum``
    first, then hand out the remaining budget proportionally.
    """
    by_stratum: Dict[str, List[tuple[str, str, str]]] = defaultdict(list)
    for item in candidates:
        by_stratum[item[1]].append(item)

    strata = sorted(by_stratum)
    total = len(candidates)
    if max_docs >= total:
        return list(candidates)

    quota: Dict[str, int] = {}
    for s in strata:
        quota[s] = min(min_per_stratum, len(by_stratum[s]))

    floor_used = sum(quota.values())
    remaining = max_docs - floor_used
    if remaining <= 0:
        # Even the floor overshoots the budget: keep the floor but trim the
        # largest strata back. Log-visible via the caller's summary.
        overshoot = floor_used - max_docs
        for s in sorted(strata, key=lambda x: -quota[x]):
            if overshoot <= 0:
                break
            take = min(overshoot, max(quota[s] - 1, 0))
            quota[s] -= take
            overshoot -= take
    else:
        headroom = {s: len(by_stratum[s]) - quota[s] for s in strata}
        pool = sum(headroom.values())
        if pool > 0:
            assigned = 0
            fractional: List[tuple[float, str]] = []
            for s in strata:
                exact = remaining * headroom[s] / pool
                whole = int(exact)
                quota[s] += whole
                assigned += whole
                fractional.append((exact - whole, s))
            # Distribute the rounding remainder by largest fractional part.
            fractional.sort(reverse=True)
            for _frac, s in fractional[: remaining - assigned]:
                if quota[s] < len(by_stratum[s]):
                    quota[s] += 1

    rng = random.Random(seed)
    picked: List[tuple[str, str, str]] = []
    for s in strata:
        bucket = by_stratum[s]
        k = min(quota[s], len(bucket))
        if k <= 0:
            continue
        if k == len(bucket):
            picked.extend(bucket)
        else:
            picked.extend(rng.sample(bucket, k))

    picked.sort(key=lambda t: t[0])
    return picked


def build_manifest(cfg: CorpusSettings, manifest_path: str) -> List[ManifestEntry]:
    """Scan the corpus, optionally sample, and freeze the result to disk."""
    log.info("[corpus] scanning %s ...", cfg.root)
    candidates = _scan_candidates(cfg)
    log.info("[corpus] found %d candidate documents", len(candidates))

    if cfg.max_docs is not None and cfg.max_docs < len(candidates):
        if cfg.stratify:
            log.info(
                "[corpus] stratified sampling to max_docs=%d "
                "(stratum_depth=%d, min_per_stratum=%d, seed=%d)",
                cfg.max_docs,
                cfg.stratum_depth,
                cfg.min_per_stratum,
                cfg.sampling_seed,
            )
            selected = stratified_sample(
                candidates, cfg.max_docs, cfg.min_per_stratum, cfg.sampling_seed
            )
        else:
            log.info("[corpus] uniform random sampling to max_docs=%d", cfg.max_docs)
            rng = random.Random(cfg.sampling_seed)
            selected = sorted(rng.sample(list(candidates), cfg.max_docs))
    else:
        log.info("[corpus] FULL SCAN: using all %d documents", len(candidates))
        selected = list(candidates)

    entries: List[ManifestEntry] = []
    for i, (rel, stratum, source) in enumerate(selected):
        entries.append(
            ManifestEntry(
                doc_index=i,
                doc_id=_derive_doc_id(rel),
                rel_path=rel,
                stratum=stratum,
                source=source,
                title="",
            )
        )

    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    tmp = manifest_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(e.to_json() + "\n")
    os.replace(tmp, manifest_path)

    by_source: Dict[str, int] = defaultdict(int)
    for e in entries:
        by_source[e.source] += 1
    log.info("[corpus] manifest frozen: %d documents -> %s", len(entries), manifest_path)
    for s in sorted(by_source, key=lambda k: -by_source[k]):
        log.info("[corpus]   %-16s %7d", s, by_source[s])
    return entries


def load_manifest(manifest_path: str) -> List[ManifestEntry]:
    entries: List[ManifestEntry] = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(ManifestEntry.from_json(line))
    for i, e in enumerate(entries):
        if e.doc_index != i:
            raise ValueError(
                f"manifest is not contiguous at row {i} (doc_index={e.doc_index}); "
                "delete work/ and rebuild"
            )
    return entries


def manifest_fingerprint(entries: Sequence[ManifestEntry]) -> str:
    """Hash of the manifest identity, used to invalidate the embedding cache."""
    h = hashlib.sha256()
    h.update(str(len(entries)).encode())
    for e in entries:
        h.update(e.rel_path.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:32]


def iter_documents(
    root: str, entries: Sequence[ManifestEntry], start: int, end: int
) -> Iterator[Document]:
    """Read documents for manifest rows [start, end)."""
    for e in entries[start:end]:
        try:
            yield read_document(root, e)
        except OSError as exc:
            log.warning("[corpus] unreadable %s: %s", e.rel_path, exc)
            yield Document(
                doc_index=e.doc_index,
                doc_id=e.doc_id,
                rel_path=e.rel_path,
                stratum=e.stratum,
                source=e.source,
                title=e.title or os.path.basename(e.rel_path),
                body="",
            )
