"""
SQLite metadata store for the Document Import feature (MVP).

Raw ``sqlite3`` (no ORM), mirroring the style already used in the project
(``kb_classifier/common/vector_store.py``): WAL mode, a single small table, and
plain helper functions. This is the source of truth for imported-document
metadata.

Lifecycle of a row:
    pending   -> created by POST /api/documents/import (file in temp storage,
                 classification already computed and stored)
    imported  -> after POST /api/documents/import/{id}/confirm (file moved to
                 permanent sharded storage)

``classification_status`` is the simplified user-facing value ("classified" or
"unknown"); ``raw_status`` keeps the classifier's precise status
(ASSIGNED/PARTIAL/FALLBACK/UNKNOWN) for debugging.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import lifecycle states.
STATE_PENDING = "pending"      # classified, file in temp, awaiting confirm
STATE_IMPORTED = "imported"    # confirmed, file in permanent storage

# Simplified classification status (user-facing).
CLS_CLASSIFIED = "classified"
CLS_UNKNOWN = "unknown"

# classification_source values.
SRC_AUTOMATIC = "automatic"
SRC_MANUAL = "manual"

_COLUMNS = [
    "id",
    "original_filename",
    "storage_path",
    "import_state",
    "taxonomy_version",
    "category_level_1",
    "category_level_2",
    "category_level_3",
    "classification_status",
    "classification_source",
    "raw_status",
    "created_at",
    "updated_at",
]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class ImportDB:
    """Thin SQLite wrapper for imported-document metadata."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so the singleton can serve requests from the
        # threadpool FastAPI uses for sync endpoints. Access is serialized by
        # SQLite + our short transactions; this MVP is single-file/low-volume.
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents_import (
                id                     TEXT PRIMARY KEY,
                original_filename      TEXT NOT NULL,
                storage_path           TEXT,
                import_state           TEXT NOT NULL,
                taxonomy_version       TEXT,
                category_level_1       TEXT,
                category_level_2       TEXT,
                category_level_3       TEXT,
                classification_status  TEXT NOT NULL,
                classification_source  TEXT NOT NULL,
                raw_status             TEXT,
                created_at             TEXT NOT NULL,
                updated_at             TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    def insert(self, record: Dict[str, Any]) -> None:
        """Insert a new import record. Sets created_at/updated_at."""
        now = _now()
        record = {**record}
        record.setdefault("created_at", now)
        record["updated_at"] = now
        cols = [c for c in _COLUMNS if c in record]
        placeholders = ",".join("?" for _ in cols)
        self._conn.execute(
            f"INSERT INTO documents_import ({','.join(cols)}) VALUES ({placeholders})",
            [record[c] for c in cols],
        )
        self._conn.commit()

    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM documents_import WHERE id = ?", (doc_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def update(self, doc_id: str, fields: Dict[str, Any]) -> None:
        """Update selected columns for a record and bump updated_at."""
        fields = {k: v for k, v in fields.items() if k in _COLUMNS and k != "id"}
        fields["updated_at"] = _now()
        assignments = ",".join(f"{k} = ?" for k in fields)
        self._conn.execute(
            f"UPDATE documents_import SET {assignments} WHERE id = ?",
            [*fields.values(), doc_id],
        )
        self._conn.commit()

    def list_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM documents_import ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass
