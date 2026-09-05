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
    "level_scores",
    "document_body",
    "file_size",
    "source",
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
                level_scores           TEXT,
                document_body          TEXT,
                file_size              INTEGER,
                source                 TEXT,
                created_at             TEXT NOT NULL,
                updated_at             TEXT NOT NULL
            )
            """
        )
        # Lightweight migration: add columns introduced after the first schema.
        existing = {r[1] for r in self._conn.execute("PRAGMA table_info(documents_import)")}
        if "file_size" not in existing:
            self._conn.execute("ALTER TABLE documents_import ADD COLUMN file_size INTEGER")
        if "source" not in existing:
            self._conn.execute("ALTER TABLE documents_import ADD COLUMN source TEXT")
        if "level_scores" not in existing:
            self._conn.execute("ALTER TABLE documents_import ADD COLUMN level_scores TEXT")
        self._conn.commit()

    # ------------------------------------------------------------------
    def insert(self, record: Dict[str, Any]) -> None:
        """Insert a new import record. Sets created_at/updated_at."""
        now = _now()
        record = {**record}
        record.setdefault("created_at", now)
        record["updated_at"] = now
        existing = {r[1] for r in self._conn.execute("PRAGMA table_info(documents_import)")}
        cols = [c for c in _COLUMNS if c in record and c in existing]
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

    # ------------------------------------------------------------------
    # browsing / pagination / preview
    # ------------------------------------------------------------------
    def list_documents(
        self,
        category_level_1: Optional[str] = None,
        category_level_2: Optional[str] = None,
        category_level_3: Optional[str] = None,
        import_state: Optional[str] = STATE_IMPORTED,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Paginated document listing, optionally filtered by category path.

        Returns (rows, total_count). Rows exclude the heavy document_body.
        """
        where: List[str] = []
        params: List[Any] = []
        if import_state:
            where.append("import_state = ?")
            params.append(import_state)
        for col, val in (
            ("category_level_1", category_level_1),
            ("category_level_2", category_level_2),
            ("category_level_3", category_level_3),
        ):
            if val:
                where.append(f"{col} = ?")
                params.append(val)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        total = self._conn.execute(
            f"SELECT COUNT(*) FROM documents_import {where_sql}", params
        ).fetchone()[0]

        page = max(1, page)
        page_size = max(1, min(page_size, 200))
        cols = ",".join(c for c in _COLUMNS if c != "document_body")
        rows = self._conn.execute(
            f"SELECT {cols} FROM documents_import {where_sql} "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
        return [dict(r) for r in rows], total

    def count_by_l3(self, import_state: Optional[str] = STATE_IMPORTED) -> Dict[tuple, int]:
        """Document counts grouped by (L1, L2, L3) category names."""
        where = "WHERE import_state = ?" if import_state else ""
        params: tuple = (import_state,) if import_state else ()
        rows = self._conn.execute(
            "SELECT category_level_1, category_level_2, category_level_3, COUNT(*) AS n "
            f"FROM documents_import {where} "
            "GROUP BY category_level_1, category_level_2, category_level_3",
            params,
        ).fetchall()
        return {
            (r["category_level_1"], r["category_level_2"], r["category_level_3"]): r["n"]
            for r in rows
        }

    def get_preview(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single document including its body (for preview)."""
        return self.get(doc_id)
