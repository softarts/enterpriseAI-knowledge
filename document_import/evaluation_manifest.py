"""Build a deterministic source-file manifest from evaluation queries."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable


def build_manifest(query_file: Path, source_root: Path) -> Dict[str, Any]:
    """Extract unique expected source files and validate their mappings."""
    data = json.loads(Path(query_file).read_text(encoding="utf-8"))
    queries = data.get("queries")
    if not isinstance(queries, list):
        raise ValueError("evaluation query file must contain a queries list")
    if data.get("query_count") is not None and data["query_count"] != len(queries):
        raise ValueError("query_count does not match the queries list")

    root = Path(source_root).resolve()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for query in queries:
        source_path = str(query.get("expected_source_path", "")).strip()
        document_id = str(query.get("expected_document_id", "")).strip()
        if not source_path or not document_id:
            raise ValueError(f"query {query.get('id', '<unknown>')} lacks source path or document ID")
        relative = Path(source_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"source path escapes source root: {source_path}")
        grouped[source_path].append(query)

    files = []
    for source_path in sorted(grouped):
        queries_for_file = grouped[source_path]
        document_ids = {str(q["expected_document_id"]) for q in queries_for_file}
        if len(document_ids) != 1:
            raise ValueError(f"source path maps to multiple document IDs: {source_path}")
        resolved = (root / source_path).resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise FileNotFoundError(f"source file does not exist under {root}: {source_path}")
        files.append({
            "source_path": source_path,
            "document_id": next(iter(document_ids)),
            "query_ids": sorted(str(q["id"]) for q in queries_for_file),
            "expected_headings": sorted({str(q.get("expected_heading", "")) for q in queries_for_file if q.get("expected_heading")}),
        })

    return {
        "version": "1.0",
        "manifest_id": "evaluation-sources-v1",
        "query_file": str(Path(query_file)),
        "query_count": len(queries),
        "file_count": len(files),
        "files": files,
    }


def write_manifest(manifest: Dict[str, Any], output: Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an evaluation source manifest")
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    manifest = build_manifest(args.queries, args.source_root)
    write_manifest(manifest, args.output)
    print(f"queries={manifest['query_count']} files={manifest['file_count']} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
