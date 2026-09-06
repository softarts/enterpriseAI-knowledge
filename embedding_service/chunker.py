"""Deterministic, Markdown-first document chunking.

The chunker deliberately knows nothing about an embedding model.  A caller may
inject a model tokenizer, but the default counter is deterministic and has no
third-party/model dependency.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple


TokenCounter = Callable[[str], int]
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_SENTENCE_RE = re.compile(r"(?<=[.!?。！？])(?:\s+|$)")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    title: str
    heading: Optional[str]
    content: str
    source_path: str
    version: Optional[str] = None
    chunk_index: int = 0
    heading_path: Tuple[str, ...] = field(default_factory=tuple)
    content_hash: str = ""
    token_count: int = 0
    chunk_version: str = "v1"
    offsets: Optional[Tuple[int, int]] = None


def default_token_count(text: str) -> int:
    """A stable approximation used when no tokenizer is injected."""
    return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))


def _trimmed_span(text: str, start: int, end: int) -> Optional[Tuple[int, int]]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


def _spans_for_delimiter(text: str, start: int, end: int, pattern: re.Pattern[str]) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    cursor = start
    for match in pattern.finditer(text, start, end):
        piece_end = match.start()
        span = _trimmed_span(text, cursor, piece_end)
        if span:
            spans.append(span)
        cursor = match.end()
    span = _trimmed_span(text, cursor, end)
    if span:
        spans.append(span)
    return spans


def _token_spans(text: str, start: int, end: int, counter: TokenCounter, max_tokens: int) -> List[Tuple[int, int]]:
    """Split an overlarge sentence without using text.find()."""
    tokens = list(re.finditer(r"\S+", text, re.UNICODE,))
    selected = [m for m in tokens if start <= m.start() and m.end() <= end]
    spans: List[Tuple[int, int]] = []
    for i in range(0, len(selected), max_tokens):
        group = selected[i : i + max_tokens]
        if group:
            spans.append((group[0].start(), group[-1].end()))
    return spans


def _make_chunk(
    *, document_id: str, title: str, source_path: str, version: Optional[str], heading_path: Sequence[str],
    text: str, start: int, end: int, index: int, counter: TokenCounter, chunk_version: str,
) -> Chunk:
    content = text[start:end]
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    identity = "\0".join([document_id, str(version or ""), "/".join(heading_path), str(start), str(end), content_hash, chunk_version])
    chunk_id = f"{document_id}-chunk-{index:03d}-{hashlib.sha256(identity.encode()).hexdigest()[:12]}"
    return Chunk(
        chunk_id=chunk_id, document_id=document_id, title=title,
        heading=heading_path[-1] if heading_path else None, content=content,
        source_path=source_path, version=version, chunk_index=index,
        heading_path=tuple(heading_path), content_hash=content_hash,
        token_count=counter(content), chunk_version=chunk_version, offsets=(start, end),
    )


def chunk_document(
    document_id: str, title: str, content: str, source_path: str,
    version: Optional[str] = None, tokenizer: Optional[TokenCounter] = None,
    target_tokens: int = 700, min_tokens: int = 150, max_tokens: int = 1100,
    overlap_ratio: float = 0.12, chunk_version: str = "v1",
) -> List[Chunk]:
    """Chunk Markdown by heading sections, splitting only oversized sections.

    Heading lines are metadata and are excluded from content.  Oversized
    sections split paragraph-first, sentence-second, and token-last.  Packing
    and overlap are confined to one section, making results deterministic and
    preventing heading leakage.
    """
    if not content.strip():
        return []
    counter = tokenizer or default_token_count
    headings = list(_HEADING_RE.finditer(content))
    sections: List[Tuple[Tuple[str, ...], int, int]] = []
    if headings:
        pre = _trimmed_span(content, 0, headings[0].start())
        if pre:
            sections.append((tuple(), *pre))
        hierarchy: List[str] = []
        levels: List[int] = []
        for i, match in enumerate(headings):
            level = len(match.group(1))
            while levels and levels[-1] >= level:
                levels.pop(); hierarchy.pop()
            hierarchy.append(match.group(2).strip()); levels.append(level)
            body = _trimmed_span(content, match.end(), headings[i + 1].start() if i + 1 < len(headings) else len(content))
            if body:
                sections.append((tuple(hierarchy), *body))
    else:
        body = _trimmed_span(content, 0, len(content))
        if body:
            sections.append((tuple(), *body))

    result: List[Chunk] = []
    overlap_tokens = max(1, round(max_tokens * overlap_ratio))
    for path, section_start, section_end in sections:
        section_tokens = counter(content[section_start:section_end])
        spans: List[Tuple[int, int]] = [(section_start, section_end)]
        if section_tokens > max_tokens:
            paragraphs = _spans_for_delimiter(content, section_start, section_end, re.compile(r"\n\s*\n+"))
            units: List[Tuple[int, int]] = []
            for p_start, p_end in paragraphs:
                if counter(content[p_start:p_end]) <= max_tokens:
                    units.append((p_start, p_end)); continue
                sentences = _spans_for_delimiter(content, p_start, p_end, _SENTENCE_RE)
                for s_start, s_end in sentences:
                    if counter(content[s_start:s_end]) <= max_tokens:
                        units.append((s_start, s_end))
                    else:
                        units.extend(_token_spans(content, s_start, s_end, counter, max_tokens))
            spans = []
            current: List[Tuple[int, int]] = []
            current_tokens = 0
            for unit in units:
                unit_tokens = counter(content[unit[0]:unit[1]])
                if current and current_tokens + unit_tokens > target_tokens:
                    spans.append((current[0][0], current[-1][1]))
                    tail: List[Tuple[int, int]] = []
                    tail_tokens = 0
                    for old in reversed(current):
                        n = counter(content[old[0]:old[1]])
                        if tail_tokens + n > overlap_tokens: break
                        tail.insert(0, old); tail_tokens += n
                    current, current_tokens = tail, tail_tokens
                current.append(unit); current_tokens += unit_tokens
            if current:
                spans.append((current[0][0], current[-1][1]))
        for start, end in spans:
            result.append(_make_chunk(document_id=document_id, title=title, source_path=source_path, version=version,
                                      heading_path=path, text=content, start=start, end=end, index=len(result),
                                      counter=counter, chunk_version=chunk_version))
    return result
