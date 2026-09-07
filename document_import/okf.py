"""Model-neutral OKF parser and document record."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_DOCUMENT_ID_LINE_RE = re.compile(r"^document_id\s*:.*$", re.MULTILINE)


@dataclass(frozen=True)
class OKFDocument:
    """The parsed shape consumed by downstream pipeline services."""

    document_id: str
    title: str
    author: str = "unknown"
    created_at: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    source_path: str = ""
    content: str = ""
    file_path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        return value


def _generated_document_id(file_path: Path) -> str:
    stem = file_path.with_suffix("").as_posix()
    return re.sub(r"-+", "-", stem.replace("_", "-").replace("/", "-")).lower().strip("-")


def parse_okf_file(file_path: Path) -> OKFDocument:
    """Parse one OKF YAML+Markdown file without importing doc_service."""
    path = Path(file_path)
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError(f"No valid YAML frontmatter found in {path}")
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML frontmatter in {path}: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f"OKF frontmatter must be a mapping in {path}")
    return OKFDocument(
        document_id=str(metadata.get("document_id") or _generated_document_id(path)),
        title=str(metadata.get("title", "")),
        author=str(metadata.get("author", "unknown")),
        created_at=metadata.get("created_at"),
        tags=list(metadata.get("tags", []) or []),
        source_path=str(metadata.get("source_path", "")),
        content=match.group(2).strip(),
        file_path=str(path),
        metadata=metadata,
    )


def set_okf_document_id(okf_content: str, document_id: str) -> str:
    """Replace the OKF identity while preserving its Markdown body."""
    match = _FRONTMATTER_RE.match(okf_content)
    if not match:
        raise ValueError("No valid YAML frontmatter found")
    frontmatter = match.group(1)
    replacement = f"document_id: {document_id}"
    if _DOCUMENT_ID_LINE_RE.search(frontmatter):
        frontmatter = _DOCUMENT_ID_LINE_RE.sub(replacement, frontmatter, count=1)
    else:
        frontmatter = f"document_id: {document_id}\n{frontmatter}"
    return f"---\n{frontmatter}\n---\n{match.group(2)}"


def print_okf_record(file_path: Path) -> None:
    """Print a stable, JSON-serializable representation for CLI inspection."""
    print(json.dumps(parse_okf_file(file_path).to_dict(), ensure_ascii=False, indent=2, default=str))
