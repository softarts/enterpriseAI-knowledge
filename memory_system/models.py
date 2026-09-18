"""
memory_system.models — Domain dataclasses shared across all modules.

Design principle:
    SQLite is the source of truth for all conversation and memory metadata.
    Chroma is the vector retrieval index only.

    Memory.source_turn_id links every memory back to the original raw turn
    in SQLite, enabling source hydration in the retrieval pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class MemoryStatus(str, Enum):
    """Lifecycle status of a memory entry."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"


@dataclass
class Conversation:
    """A conversation session."""

    id: str
    created_at: datetime
    updated_at: datetime


@dataclass
class Turn:
    """A single conversation turn (user or assistant)."""

    id: str
    conversation_id: str
    role: str          # "user" | "assistant"
    content: str
    created_at: datetime


@dataclass
class Memory:
    """
    A semantic index entry for a conversation turn.

    Memory is NOT a knowledge base entry — it is a retrieval index
    that points back to the original raw turn via source_turn_id.

    memory.content  → one-sentence semantic theme description
    source_turn_id  → foreign key into SQLite turns table (source of truth)
    """

    id: str
    conversation_id: str
    source_turn_id: str          # points to the user turn that generated this memory
    content: str                 # semantic theme description (NOT a knowledge base entry)
    status: MemoryStatus
    created_at: datetime
    updated_at: datetime


@dataclass
class RetrievedMemory:
    """
    A memory returned from retrieval, optionally hydrated with the source turn.

    Hydration:
        After retrieval, the pipeline fetches the raw source turn from SQLite
        via memory.source_turn_id. This raw turn (not the memory.content alone)
        forms the factual historical context for the LLM.
    """

    memory: Memory
    similarity: float
    source_turn: Optional[Turn] = None  # populated during source hydration


@dataclass
class AssembledContext:
    """Final context passed to the LLM."""

    system_prompt: str
    recent_turns: List[Turn] = field(default_factory=list)
    retrieved_memories: List[RetrievedMemory] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM structured output schemas (used as Pydantic-like plain dataclasses)
# ---------------------------------------------------------------------------

@dataclass
class RewriteOutput:
    """Structured output from query rewrite LLM call."""
    rewritten_query: str


@dataclass
class ExtractOutput:
    """Structured output from memory extraction LLM call."""
    should_store: bool
    content: str


@dataclass
class DedupOutput:
    """Structured output from dedup judgment LLM call."""
    decision: str  # "duplicate" | "update" | "distinct"
