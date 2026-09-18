"""
memory_system.storage.sqlite_store — SQLite persistence layer.

SQLite is the SOURCE OF TRUTH for:
  - Raw conversation turns
  - Memory metadata (id, status, source_turn_id, content)

Chroma holds only embedding vectors + minimal metadata for retrieval.
Any authoritative data lives here.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, List, Optional

from memory_system.models import Conversation, Memory, MemoryStatus, Turn

logger = logging.getLogger(__name__)

_DATETIME_FMT = "%Y-%m-%dT%H:%M:%S.%f"


def _now() -> datetime:
    return datetime.utcnow()


def _fmt(dt: datetime) -> str:
    return dt.strftime(_DATETIME_FMT)


def _parse(s: str) -> datetime:
    try:
        return datetime.strptime(s, _DATETIME_FMT)
    except ValueError:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")


class SQLiteStore:
    """
    Manages conversations, turns, and memory metadata in SQLite.

    All write operations are committed immediately (autocommit-style)
    to keep the MVP simple and reliable.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        logger.info("SQLiteStore initialised: path=%s", db_path)

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """Create tables if they do not already exist."""
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id         TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS turns (
                    id              TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role            TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    created_at      TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id              TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    source_turn_id  TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'active',
                    created_at      TEXT NOT NULL,
                    updated_at      TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                    FOREIGN KEY (source_turn_id)  REFERENCES turns(id)
                );

                CREATE INDEX IF NOT EXISTS idx_turns_conv
                    ON turns (conversation_id);
                CREATE INDEX IF NOT EXISTS idx_memories_conv
                    ON memories (conversation_id);
                CREATE INDEX IF NOT EXISTS idx_memories_status
                    ON memories (status);
                """
            )
        logger.info("SQLite schema initialised.")

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    def create_conversation(self, conversation_id: Optional[str] = None) -> Conversation:
        """Insert a new conversation row and return the domain object."""
        conv_id = conversation_id or str(uuid.uuid4())
        now = _now()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, created_at, updated_at) VALUES (?, ?, ?)",
                (conv_id, _fmt(now), _fmt(now)),
            )
        conv = Conversation(id=conv_id, created_at=now, updated_at=now)
        logger.debug("Created conversation: id=%s", conv_id)
        return conv

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        if row is None:
            return None
        return Conversation(
            id=row["id"],
            created_at=_parse(row["created_at"]),
            updated_at=_parse(row["updated_at"]),
        )

    # ------------------------------------------------------------------
    # Turns
    # ------------------------------------------------------------------

    def save_turn(
        self,
        conversation_id: str,
        role: str,
        content: str,
        turn_id: Optional[str] = None,
    ) -> Turn:
        """Persist a turn and return the domain object."""
        tid = turn_id or str(uuid.uuid4())
        now = _now()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO turns (id, conversation_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (tid, conversation_id, role, content, _fmt(now)),
            )
        turn = Turn(
            id=tid,
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=now,
        )
        logger.debug("Saved turn: id=%s role=%s conv=%s", tid, role, conversation_id)
        return turn

    def get_turn_by_id(self, turn_id: str) -> Optional[Turn]:
        """Fetch a raw turn by id — used during source hydration."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM turns WHERE id = ?", (turn_id,)
            ).fetchone()
        if row is None:
            return None
        return Turn(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row["content"],
            created_at=_parse(row["created_at"]),
        )

    def get_recent_turns(self, conversation_id: str, n: int) -> List[Turn]:
        """Return the most recent n turns for a conversation, in chronological order."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM turns
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ) sub
                ORDER BY created_at ASC
                """,
                (conversation_id, n),
            ).fetchall()
        return [
            Turn(
                id=r["id"],
                conversation_id=r["conversation_id"],
                role=r["role"],
                content=r["content"],
                created_at=_parse(r["created_at"]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Memories
    # ------------------------------------------------------------------

    def save_memory(
        self,
        conversation_id: str,
        source_turn_id: str,
        content: str,
        memory_id: Optional[str] = None,
    ) -> Memory:
        """Insert a new active memory and return the domain object."""
        mid = memory_id or str(uuid.uuid4())
        now = _now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO memories
                    (id, conversation_id, source_turn_id, content, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (mid, conversation_id, source_turn_id, content, MemoryStatus.ACTIVE.value, _fmt(now), _fmt(now)),
            )
        mem = Memory(
            id=mid,
            conversation_id=conversation_id,
            source_turn_id=source_turn_id,
            content=content,
            status=MemoryStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        logger.debug("Saved memory: id=%s conv=%s", mid, conversation_id)
        return mem

    def deprecate_memory(self, memory_id: str) -> None:
        """Mark a memory as deprecated so it is excluded from retrieval."""
        now = _now()
        with self._conn() as conn:
            conn.execute(
                "UPDATE memories SET status = ?, updated_at = ? WHERE id = ?",
                (MemoryStatus.DEPRECATED.value, _fmt(now), memory_id),
            )
        logger.info("Deprecated memory: id=%s", memory_id)

    def get_memory_by_id(self, memory_id: str) -> Optional[Memory]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        if row is None:
            return None
        return _row_to_memory(row)

    def get_active_memories(self, conversation_id: str) -> List[Memory]:
        """Return all active memories for a conversation."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE conversation_id = ? AND status = ?",
                (conversation_id, MemoryStatus.ACTIVE.value),
            ).fetchall()
        return [_row_to_memory(r) for r in rows]


def _row_to_memory(row: sqlite3.Row) -> Memory:
    return Memory(
        id=row["id"],
        conversation_id=row["conversation_id"],
        source_turn_id=row["source_turn_id"],
        content=row["content"],
        status=MemoryStatus(row["status"]),
        created_at=_parse(row["created_at"]),
        updated_at=_parse(row["updated_at"]),
    )
