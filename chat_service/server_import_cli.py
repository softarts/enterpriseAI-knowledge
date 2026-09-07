"""Import a server-local manifest through the persistent batch task system."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from chat_service.config import settings


def _load_files(manifest_path: Path, source_root: Path) -> list[tuple[str, Path]]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest must contain a non-empty files list")
    root = Path(source_root).resolve()
    files = []
    for entry in entries:
        relative = Path(str(entry.get("source_path", "")))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ValueError(f"invalid source path: {relative}")
        source = (root / relative).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise FileNotFoundError(f"source file does not exist under {root}: {relative}")
        if source.suffix.lower() not in settings.import_allowed_extensions:
            raise ValueError(f"unsupported source extension: {source}")
        if source.stat().st_size == 0:
            raise ValueError(f"source file is empty: {source}")
        if source.stat().st_size > settings.import_max_bytes:
            raise ValueError(f"source file exceeds import limit: {source}")
        files.append((relative.as_posix(), source))
    return files


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a server-local batch import task")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    files = _load_files(args.manifest, args.source_root)
    if args.dry_run:
        print(json.dumps({"files": len(files), "source_root": str(args.source_root.resolve())}, indent=2))
        return 0

    from chat_service.services.batch_import_service import BatchImportService

    task = BatchImportService().create_task_from_paths(files)
    print(json.dumps({
        "task_id": task["task_id"],
        "total_files": task["total_files"],
        "status": task["status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
