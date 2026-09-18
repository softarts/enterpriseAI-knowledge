"""
memory_system.query.rewriter — Query rewriting module.

Rewrites the current user query into a standalone retrieval query by
resolving references using recent conversation turns.

Input:
    current_query: str
    recent_turns:  List[Turn]  (up to RECENT_TURNS_WINDOW turns)

Output:
    RewriteOutput.rewritten_query: str

Note: Clarify / ambiguity handling is intentionally deferred to the next task.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from memory_system.llm.client import LLMClient
from memory_system.models import RewriteOutput, Turn

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "rewrite.txt"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


class QueryRewriter:
    """
    Rewrites user queries to be suitable for semantic retrieval.

    Resolves follow-up references (pronouns, ellipsis, etc.) using
    the recent conversation turns as context.
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client
        self._system_prompt = _load_prompt()

    def rewrite(self, current_query: str, recent_turns: List[Turn]) -> RewriteOutput:
        """
        Rewrite the current query for retrieval.

        Args:
            current_query: The raw user query from the current turn.
            recent_turns:  Recent conversation turns (chronological order).

        Returns:
            RewriteOutput with the rewritten query string.
        """
        turns_text = "\n".join(
            f"{t.role}: {t.content}" for t in recent_turns
        )
        user_prompt = (
            f"---\nRecent turns:\n{turns_text}\n---\n"
            f"Current query: {current_query}"
        )

        logger.info(
            "QueryRewriter: rewriting query='%s' with %d recent turns",
            current_query[:60],
            len(recent_turns),
        )

        raw = self._llm.chat_json(self._system_prompt, user_prompt)
        rewritten = raw.get("rewritten_query", current_query)

        # Fallback: if LLM returns empty, use original query
        if not rewritten or not rewritten.strip():
            logger.warning("QueryRewriter: empty rewrite, falling back to original query")
            rewritten = current_query

        logger.info("QueryRewriter: rewritten='%s'", rewritten[:80])
        return RewriteOutput(rewritten_query=rewritten)
