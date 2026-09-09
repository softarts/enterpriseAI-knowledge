"""Import a server-local manifest through the persistent batch task system."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterable

from chat_service.import_config import settings


def _load_files(manifest_path: Path, source_root: Path | None) -> list[tuple[str, Path]]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest must contain a non-empty files list")
    files = []
    for entry in entries:
        source_value = str(entry.get("source_path", "")).strip()
        source = Path(source_value)
        if not source.is_absolute():
            if source_root is None:
                raise ValueError(f"manifest source_path must be absolute: {source}")
            root = Path(source_root).resolve()
            if ".." in source.parts:
                raise ValueError(f"invalid source path: {source}")
            source = (root / source).resolve()
            if not source.is_relative_to(root):
                raise ValueError(f"source path escapes source root: {source}")
        else:
            source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"source file does not exist: {source}")
        if source.suffix.lower() not in settings.import_allowed_extensions:
            raise ValueError(f"unsupported source extension: {source}")
        if source.stat().st_size == 0:
            raise ValueError(f"source file is empty: {source}")
        if source.stat().st_size > settings.import_max_bytes:
            raise ValueError(f"source file exceeds import limit: {source}")
        expected_hash = str(entry.get("content_hash", "")).removeprefix("sha256:")
        actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if expected_hash and expected_hash != actual_hash:
            raise ValueError(f"content hash mismatch for {source}")
        source_key = str(entry.get("source_path_key", source.name)).replace("\\", "/")
        files.append((source_key, source))
    return files


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a server-local batch import task")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--wait", action="store_true", help="wait until the worker finishes")
    parser.add_argument("--timeout", type=int, default=3600, help="maximum wait time in seconds")
    args = parser.parse_args(list(argv) if argv is not None else None)

    files = _load_files(args.manifest, args.source_root)
    if args.dry_run:
        print(json.dumps({"files": len(files)}, indent=2))
        return 0

    from chat_service.services.batch_import_service import BatchImportService

    task = BatchImportService().create_task_from_paths(files)
    if args.wait:
        service = BatchImportService()
        deadline = time.monotonic() + args.timeout
        while True:
            detail = service.detail(task["task_id"])
            if detail["status"] == "completed":
                task = detail
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(f"batch task did not finish within {args.timeout}s: {task['task_id']}")
            time.sleep(1)
    print(json.dumps({
        "task_id": task["task_id"],
        "total_files": task["total_files"],
        "status": task["status"],
        "failed_files": task.get("failed_files", 0),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
