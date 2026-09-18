"""
memory_system.context.assembler — Context assembly for LLM prompt.

Assembles the final prompt context from three distinct sources:

    1. system_prompt:
       Baseline instructions for the assistant. (~200 token budget)

    2. recent_turns (recent conversation context):
       The last N turns of the current conversation, providing immediate
       conversational continuity. These are NOT historical memories.
       Budget: TOKEN_BUDGET_RECENT chars.

    3. retrieved_historical_context (retrieved semantic memory):
       Source turns hydrated from SQLite via retrieved memory's source_turn_id.
       These are HISTORICAL turns from earlier in the conversation (5+ turns ago).
       The memory.content provides the semantic theme; the source turn provides
       the actual factual content. Budget: TOKEN_BUDGET_HISTORICAL chars.

Key design: recent_turns and retrieved_historical_context serve different roles
and must NOT be conflated. Recent turns give continuity; historical context
gives depth for follow-up questions.

Token budget:
    Approximate: 1 token ≈ 4 characters (simple, no tokenizer dependency).
    If a section exceeds budget, it is truncated from the end with a marker.
    recent_turns and retrieved_historical_context have independent budgets
    so neither can completely crowd out the other.
"""

from __future__ import annotations

import logging
from typing import List

from memory_system import config
from memory_system.models import AssembledContext, RetrievedMemory, Turn

logger = logging.getLogger(__name__)

# Approximate chars-per-token ratio (conservative estimate)
_CHARS_PER_TOKEN = 4


def _token_to_chars(token_budget: int) -> int:
    return token_budget * _CHARS_PER_TOKEN


def _truncate(text: str, char_limit: int) -> str:
    """Truncate text to char_limit, appending a marker if truncated."""
    if len(text) <= char_limit:
        return text
    return text[:char_limit] + "\n[... truncated for token budget ...]"


class ContextAssembler:
    """
    Assembles the final LLM context from system prompt, recent turns,
    and retrieved historical context (hydrated source turns).
    """

    def __init__(self) -> None:
        self._recent_char_limit = _token_to_chars(config.TOKEN_BUDGET_RECENT)
        self._historical_char_limit = _token_to_chars(config.TOKEN_BUDGET_HISTORICAL)

    def assemble(
        self,
        system_prompt: str,
        recent_turns: List[Turn],
        retrieved_memories: List[RetrievedMemory],
    ) -> AssembledContext:
        """
        Build the assembled context object.

        Args:
            system_prompt:       Static system instructions.
            recent_turns:        Most recent N turns (conversational continuity).
            retrieved_memories:  Memories with hydrated source_turn set.

        Returns:
            AssembledContext with all three sections, each within budget.
        """
        logger.info(
            "ContextAssembler: recent_turns=%d retrieved_memories=%d",
            len(recent_turns),
            len(retrieved_memories),
        )
        return AssembledContext(
            system_prompt=system_prompt,
            recent_turns=recent_turns,
            retrieved_memories=retrieved_memories,
        )

    def build_llm_messages(
        self,
        assembled: AssembledContext,
        current_query: str,
    ) -> List[dict]:
        """
        Build the messages list for the LLM API call.

        Message structure:
            [system]   → system_prompt + historical context block
            [assistant] → recent turns interleaved
            [user]     → current query

        The system prompt contains the retrieved historical context so it is
        always available regardless of how recent turns are structured.

        Args:
            assembled:     AssembledContext from assemble().
            current_query: The current user turn (raw, before rewrite).

        Returns:
            List of {"role": ..., "content": ...} dicts for the API call.
        """
        # ---- Build historical context block ----
        historical_block = self._build_historical_block(assembled.retrieved_memories)
        historical_block = _truncate(historical_block, self._historical_char_limit)

        # ---- System message ----
        system_content = assembled.system_prompt
        if historical_block:
            system_content = (
                system_content
                + "\n\n"
                + "=== Relevant Historical Context (retrieved from earlier conversation) ===\n"
                + "Note: The following historical context was retrieved because it is semantically "
                + "relevant to the current question. Use it to answer follow-up questions accurately.\n\n"
                + historical_block
            )

        # ---- Recent turns block ----
        recent_block = self._build_recent_block(assembled.recent_turns)
        recent_block = _truncate(recent_block, self._recent_char_limit)

        messages: List[dict] = [{"role": "system", "content": system_content}]

        # Add recent turns as alternating user/assistant messages
        for turn in assembled.recent_turns:
            messages.append({"role": turn.role, "content": turn.content})

        # Current query as the final user message
        messages.append({"role": "user", "content": current_query})

        logger.info(
            "ContextAssembler: system_len=%d historical_block_len=%d recent_block_len=%d",
            len(system_content),
            len(historical_block),
            len(recent_block),
        )
        return messages

    def _build_historical_block(self, retrieved_memories: List[RetrievedMemory]) -> str:
        """
        Build the historical context text from hydrated source turns.

        For each retrieved memory:
        - memory.content provides the semantic theme (why this was retrieved)
        - source_turn provides the actual factual content from the raw conversation

        Both are included so the LLM understands context and specifics.
        """
        if not retrieved_memories:
            return ""

        parts: List[str] = []
        for i, rm in enumerate(retrieved_memories, start=1):
            parts.append(f"[Historical Context {i}]")
            parts.append(f"Topic: {rm.memory.content}")
            if rm.source_turn is not None:
                parts.append(f"Original {rm.source_turn.role}: {rm.source_turn.content}")
            else:
                # Source turn not hydrated — fall back to memory content
                parts.append(f"(source turn not available)")
            parts.append("")  # blank line between entries

        return "\n".join(parts)

    def _build_recent_block(self, recent_turns: List[Turn]) -> str:
        """Build a text representation of recent turns (for logging/budget calc)."""
        return "\n".join(f"{t.role}: {t.content}" for t in recent_turns)


# System prompt template used by service.py
SYSTEM_PROMPT = (
    "You are a helpful enterprise AI assistant. "
    "Answer the user's question accurately and concisely. "
    "If relevant historical context is provided above, use it to answer follow-up questions. "
    "If you are unsure about something, say so clearly."
)
