"""Safe maintenance commands for chat_service import and vector data."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Iterable

from chat_service.config import settings
from vector_service.config import DEFAULT_VECTOR_DB_DIR

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VECTOR_DB = (PROJECT_ROOT / DEFAULT_VECTOR_DB_DIR).resolve()


def _assert_project_child(path: Path) -> Path:
    path = path.resolve()
    if not path.is_relative_to(PROJECT_ROOT) or path == PROJECT_ROOT:
        raise ValueError(f"refusing to operate outside project root: {path}")
    return path


def _targets(component: str) -> list[Path]:
    db = settings.import_db_path.resolve()
    targets: list[Path] = []
    if component in ("db", "all"):
        targets.extend([db, Path(str(db) + "-wal"), Path(str(db) + "-shm")])
    if component in ("storage", "all"):
        targets.extend([settings.import_storage_dir.resolve(), settings.import_temp_dir.resolve()])
    if component in ("chroma", "all"):
        targets.append(VECTOR_DB)
    return [_assert_project_child(target) for target in targets]


def reset(component: str, yes: bool) -> int:
    targets = _targets(component)
    print("Targets:")
    for target in targets:
        print(f"- {target}")
    if not yes:
        print("Dry run only. Add --yes to delete these targets.")
        return 0
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    for target in targets:
        if target.suffix == "" or target in (settings.import_storage_dir.resolve(), settings.import_temp_dir.resolve(), VECTOR_DB):
            if target in (settings.import_storage_dir.resolve(), settings.import_temp_dir.resolve(), VECTOR_DB):
                target.mkdir(parents=True, exist_ok=True)
    print("Reset complete.")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset chat_service import/vector data")
    parser.add_argument("reset", choices=["reset"])
    parser.add_argument("--db", action="store_true")
    parser.add_argument("--storage", action="store_true")
    parser.add_argument("--chroma", action="store_true")
    parser.add_argument("--all", action="store_true", dest="all_data")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    selected = [name for name, flag in (("db", args.db), ("storage", args.storage), ("chroma", args.chroma), ("all", args.all_data)) if flag]
    if len(selected) != 1:
        parser.error("choose exactly one of --db, --storage, --chroma, or --all")
    return reset(selected[0], args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
