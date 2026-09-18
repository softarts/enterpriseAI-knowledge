"""
memory_system.memory.extractor — Memory extraction from conversation turns.

Called ASYNCHRONOUSLY after the assistant response is returned to the user.
Must not block the main response path.

Extraction philosophy:
    Memory = semantic retrieval index entry.
    NOT a knowledge base. NOT importance ranking. NOT memory type classification.

    Every turn with stable standalone semantics gets a memory entry.
    Only trivial/context-dependent turns are skipped.

Input:  user_query + assistant_response
Output: ExtractOutput { should_store: bool, content: str }
"""

from __future__ import annotations

import logging
from pathlib import Path

from memory_system.llm.client import LLMClient
from memory_system.models import ExtractOutput

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "extract.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


class MemoryExtractor:
    """
    Extracts a semantic memory index entry from a conversation turn.

    should_store = True  → turn has stable standalone semantic theme
    should_store = False → trivial/purely contextual turn, skip indexing
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client
        self._system_prompt = _load_prompt()

    def extract(self, user_query: str, assistant_response: str) -> ExtractOutput:
        """
        Decide whether to store this turn as a memory and produce content.

        Args:
            user_query:         The user's turn content.
            assistant_response: The assistant's response content.

        Returns:
            ExtractOutput with should_store flag and content string.
        """
        user_prompt = (
            f"User turn: {user_query}\n"
            f"Assistant turn: {assistant_response}"
        )

        logger.debug(
            "MemoryExtractor: extracting turn user='%s'",
            user_query[:60],
        )

        raw = self._llm.chat_json(self._system_prompt, user_prompt)

        should_store: bool = bool(raw.get("should_store", False))
        content: str = raw.get("content", "").strip()

        # Guard: if should_store but content is empty, skip
        if should_store and not content:
            logger.warning(
                "MemoryExtractor: should_store=True but content is empty, setting should_store=False"
            )
            should_store = False

        logger.info(
            "MemoryExtractor: should_store=%s content='%s'",
            should_store,
            content[:60] if content else "",
        )
        return ExtractOutput(should_store=should_store, content=content)
