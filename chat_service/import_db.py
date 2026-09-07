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
    "stored_filename",
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
    "content_hash",
    "source",
    "created_at",
    "updated_at",
]

_BATCH_COLUMNS = [
    "task_id", "status", "stage", "total_files", "uploaded_files",
    "processed_files", "failed_files", "error", "created_at", "updated_at",
    "started_at", "completed_at",
]
_BATCH_FILE_COLUMNS = [
    "file_id", "task_id", "document_id", "relative_path", "original_filename", "temp_path",
    "status", "okf_path", "storage_path", "classification_status",
    "taxonomy_version", "category_level_1", "category_level_2", "category_level_3",
    "level_scores", "content_hash", "dedup_status", "duplicate_of",
    "error", "retry_count", "created_at", "updated_at",
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
                stored_filename        TEXT,
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
                content_hash           TEXT,
                source                 TEXT,
                created_at             TEXT NOT NULL,
                updated_at             TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS import_tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                total_files INTEGER NOT NULL,
                uploaded_files INTEGER NOT NULL DEFAULT 0,
                processed_files INTEGER NOT NULL DEFAULT 0,
                failed_files INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS import_task_files (
                file_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                document_id TEXT,
                relative_path TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                temp_path TEXT NOT NULL,
                status TEXT NOT NULL,
                okf_path TEXT,
                storage_path TEXT,
                classification_status TEXT,
                taxonomy_version TEXT,
                category_level_1 TEXT,
                category_level_2 TEXT,
                category_level_3 TEXT,
                level_scores TEXT,
                content_hash TEXT,
                dedup_status TEXT NOT NULL DEFAULT 'new',
                duplicate_of TEXT,
                error TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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
        if "stored_filename" not in existing:
            self._conn.execute("ALTER TABLE documents_import ADD COLUMN stored_filename TEXT")
        if "content_hash" not in existing:
            self._conn.execute("ALTER TABLE documents_import ADD COLUMN content_hash TEXT")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_import_content_hash "
            "ON documents_import(content_hash)"
        )
        self._conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_import_content_hash_unique "
            "ON documents_import(content_hash) WHERE content_hash IS NOT NULL"
        )
        task_file_existing = {
            r[1] for r in self._conn.execute("PRAGMA table_info(import_task_files)")
        }
        for column, definition in (
            ("document_id", "TEXT"),
            ("content_hash", "TEXT"),
            ("dedup_status", "TEXT NOT NULL DEFAULT 'new'"),
            ("duplicate_of", "TEXT"),
        ):
            if column not in task_file_existing:
                self._conn.execute(
                    f"ALTER TABLE import_task_files ADD COLUMN {column} {definition}"
                )
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

    def find_by_content_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """Return the first document imported from the exact same file bytes."""
        if not content_hash:
            return None
        row = self._conn.execute(
            "SELECT * FROM documents_import WHERE content_hash = "
            "? ORDER BY created_at ASC LIMIT 1",
            (content_hash,),
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

    # ------------------------------------------------------------------
    # Async batch tasks
    # ------------------------------------------------------------------
    def create_task(self, task_id: str, total_files: int) -> None:
        now = _now()
        self._conn.execute(
            "INSERT INTO import_tasks (task_id,status,stage,total_files,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            (task_id, "queued", "upload", total_files, now, now),
        )
        self._conn.commit()

    def add_task_file(self, record: Dict[str, Any]) -> None:
        now = _now()
        record = {**record, "created_at": now, "updated_at": now}
        cols = [c for c in _BATCH_FILE_COLUMNS if c in record]
        self._conn.execute(
            f"INSERT INTO import_task_files ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            [record[c] for c in cols],
        )
        self._conn.commit()

    def update_task(self, task_id: str, fields: Dict[str, Any]) -> None:
        fields = {k: v for k, v in fields.items() if k in _BATCH_COLUMNS and k != "task_id"}
        fields["updated_at"] = _now()
        self._conn.execute(
            f"UPDATE import_tasks SET {','.join(f'{k} = ?' for k in fields)} WHERE task_id = ?",
            [*fields.values(), task_id],
        )
        self._conn.commit()

    def update_task_file(self, file_id: str, fields: Dict[str, Any]) -> None:
        fields = {k: v for k, v in fields.items() if k in _BATCH_FILE_COLUMNS and k != "file_id"}
        fields["updated_at"] = _now()
        self._conn.execute(
            f"UPDATE import_task_files SET {','.join(f'{k} = ?' for k in fields)} WHERE file_id = ?",
            [*fields.values(), file_id],
        )
        self._conn.commit()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute("SELECT * FROM import_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def get_task_files(self, task_id: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM import_task_files WHERE task_id = ? ORDER BY relative_path, file_id", (task_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def list_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM import_tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
