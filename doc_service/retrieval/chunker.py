"""
Heading-aware Markdown chunker.

Splits OKF Markdown body into chunks based on headings.
Chunks are runtime objects only — never written back to OKF files.
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Chunk:
    """A chunk of document content, scoped to a heading section."""

    chunk_id: str
    document_id: str
    title: str
    heading: Optional[str]
    content: str
    source_path: str


# Matches markdown headings (## or deeper; # is the document title)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def chunk_document(
    document_id: str,
    title: str,
    content: str,
    source_path: str,
) -> List[Chunk]:
    """
    Split a Markdown document into heading-aware chunks.

    Strategy:
      - Split content by headings (any level).
      - Each section (heading + body until next heading) becomes one chunk.
      - If a document has no headings, the entire body is one chunk.
      - The document title heading (first # ) is treated as its own section
        only if it has body text before the next heading.

    Args:
        document_id: Stable document identifier.
        title: Document title from metadata.
        content: Markdown body (without YAML frontmatter).
        source_path: Original source file path from metadata.

    Returns:
        List of Chunk objects.
    """
    if not content.strip():
        return []

    # Find all heading positions
    headings = list(_HEADING_RE.finditer(content))

    if not headings:
        # No headings at all — entire content is one chunk
        return [
            Chunk(
                chunk_id=f"{document_id}-chunk-000",
                document_id=document_id,
                title=title,
                heading=None,
                content=content.strip(),
                source_path=source_path,
            )
        ]

    chunks: List[Chunk] = []
    chunk_index = 0

    # Handle text before the first heading (if any)
    pre_heading_text = content[: headings[0].start()].strip()
    if pre_heading_text:
        chunks.append(
            Chunk(
                chunk_id=f"{document_id}-chunk-{chunk_index:03d}",
                document_id=document_id,
                title=title,
                heading=None,
                content=pre_heading_text,
                source_path=source_path,
            )
        )
        chunk_index += 1

    # Process each heading section
    for i, match in enumerate(headings):
        heading_text = match.group(2).strip()

        # Section body: from end of this heading line to start of next heading
        section_start = match.end()
        section_end = headings[i + 1].start() if i + 1 < len(headings) else len(content)
        section_body = content[section_start:section_end].strip()

        # Skip empty sections (heading with no body)
        if not section_body:
            continue

        chunks.append(
            Chunk(
                chunk_id=f"{document_id}-chunk-{chunk_index:03d}",
                document_id=document_id,
                title=title,
                heading=heading_text,
                content=section_body,
                source_path=source_path,
            )
        )
        chunk_index += 1

    # If no chunks produced (all sections empty), fall back to full content
    if not chunks:
        chunks.append(
            Chunk(
                chunk_id=f"{document_id}-chunk-000",
                document_id=document_id,
                title=title,
                heading=None,
                content=content.strip(),
                source_path=source_path,
            )
        )

    return chunks
