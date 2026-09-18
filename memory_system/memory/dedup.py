"""
memory_system.memory.dedup — Memory deduplication.

Dedup flow:
    new memory content
        ↓
    embed → Chroma top-1 search (active memories only)
        ↓
    if no similar memory (similarity < threshold)
        → insert as distinct
        ↓
    if similarity >= threshold
        → LLM judgment
            ├── "duplicate" → discard new memory
            ├── "update"    → deprecate old + insert new
            └── "distinct"  → insert alongside existing

V1 does NOT:
    - merge memories
    - consolidate memories
    - handle expiration

DEDUP_SIMILARITY_THRESHOLD is read from config (configurable via env var).
It is NOT a hardcoded universal constant.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

from memory_system import config
from memory_system.embedding import Embedder
from memory_system.llm.client import LLMClient
from memory_system.models import DedupOutput, Memory, MemoryStatus
from memory_system.storage.sqlite_store import SQLiteStore
from memory_system.storage.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "dedup.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


class MemoryDeduplicator:
    """
    Checks new memory content against existing active memories and decides
    whether to insert, update, or discard based on embedding similarity
    and LLM judgment.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        embedder: Embedder,
        vector_store: ChromaVectorStore,
        sqlite_store: SQLiteStore,
    ) -> None:
        self._llm = llm_client
        self._embedder = embedder
        self._vector_store = vector_store
        self._sqlite_store = sqlite_store
        self._system_prompt = _load_prompt()

    def check(self, new_content: str) -> Tuple[str, Optional[Memory]]:
        """
        Check new memory content for duplicates and return a dedup decision.

        Args:
            new_content: The candidate memory content string.

        Returns:
            Tuple of (decision, existing_memory_or_None):
                decision: "insert" | "skip" | "update"
                existing_memory: The existing memory if decision is "update", else None.

        Note: "insert" means the new memory should be stored as-is.
              "skip"   means it is a duplicate; do not insert.
              "update" means deprecate existing and insert new.
        """
        threshold = config.DEDUP_SIMILARITY_THRESHOLD
        logger.info(
            "Dedup check: content='%s' threshold=%.2f",
            new_content[:60],
            threshold,
        )

        new_embedding = self._embedder.embed(new_content)

        # Search for the single most similar ACTIVE memory
        results = self._vector_store.query(
            query_embedding=new_embedding,
            top_k=1,
            where={"status": MemoryStatus.ACTIVE.value},
        )

        if not results:
            logger.info("Dedup: no existing active memories — inserting as distinct")
            return "insert", None

        existing_id, similarity, _meta = results[0]
        logger.info(
            "Dedup top-1: id=%s similarity=%.4f threshold=%.2f",
            existing_id,
            similarity,
            threshold,
        )

        if similarity < threshold:
            logger.info("Dedup: similarity below threshold — inserting as distinct")
            return "insert", None

        # Similarity >= threshold → ask LLM
        existing_memory = self._sqlite_store.get_memory_by_id(existing_id)
        if existing_memory is None:
            logger.warning(
                "Dedup: Chroma has id=%s but SQLite does not — treating as distinct",
                existing_id,
            )
            return "insert", None

        llm_decision = self._ask_llm(
            existing_content=existing_memory.content,
            new_content=new_content,
        )

        logger.info(
            "Dedup LLM judgment: decision=%s existing='%s' new='%s'",
            llm_decision.decision,
            existing_memory.content[:50],
            new_content[:50],
        )

        if llm_decision.decision == "duplicate":
            return "skip", None
        elif llm_decision.decision == "update":
            return "update", existing_memory
        else:
            # "distinct" or unexpected value → insert
            return "insert", None

    def _ask_llm(self, existing_content: str, new_content: str) -> DedupOutput:
        user_prompt = (
            f"Existing memory: {existing_content}\n"
            f"New memory: {new_content}"
        )
        raw = self._llm.chat_json(self._system_prompt, user_prompt)
        decision = raw.get("decision", "distinct")
        if decision not in {"duplicate", "update", "distinct"}:
            logger.warning("Dedup LLM returned unexpected decision: %s, defaulting to 'distinct'", decision)
            decision = "distinct"
        return DedupOutput(decision=decision)
