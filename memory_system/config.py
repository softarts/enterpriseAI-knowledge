"""
memory_system.config — All configuration loaded from environment variables.

Environment variables:
    LLM_BASE_URL                  OpenAI-compatible base URL (e.g. https://openrouter.ai/api/v1)
    LLM_MODEL                     Model ID (e.g. openai/gpt-4o-mini)
    LLM_API_KEY                   API key
    LLM_MAX_TOKENS                Max tokens for LLM output (default: 2048)
    LLM_ENABLE_THINKING           Qwen3 thinking mode (default: false)

    EMBEDDING_MODEL               Embedding model: "minilm" | "mock" (default: "minilm")
    CHROMA_PERSIST_DIR            ChromaDB persistent directory (default: memory_system/chroma_db)
    SQLITE_DB_PATH                SQLite database path (default: memory_system/memory.db)

    RECENT_TURNS_WINDOW           Number of recent turns for query rewrite context (default: 3)
    RETRIEVAL_TOP_K               Number of memories to retrieve (default: 3)
    DEDUP_SIMILARITY_THRESHOLD    Cosine similarity threshold for dedup (default: 0.90)

    TOKEN_BUDGET_SYSTEM           Approximate token budget for system prompt (default: 200)
    TOKEN_BUDGET_RECENT           Approximate token budget for recent turns (default: 800)
    TOKEN_BUDGET_HISTORICAL       Approximate token budget for retrieved historical context (default: 600)
"""

import os
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

LLM_BASE_URL: str = os.environ.get("LLM_BASE_URL", "")
LLM_MODEL: str = os.environ.get("LLM_MODEL", "")
LLM_API_KEY: str = os.environ.get("LLM_API_KEY", "")
LLM_MAX_TOKENS: int = int(os.environ.get("LLM_MAX_TOKENS", "2048"))

_thinking_env = os.environ.get("LLM_ENABLE_THINKING")
LLM_ENABLE_THINKING: Optional[bool] = (
    None
    if _thinking_env is None
    else _thinking_env.strip().lower() in {"1", "true", "yes", "on"}
)

# ---------------------------------------------------------------------------
# Embedding
# "minilm" → sentence-transformers all-MiniLM-L6-v2 (dim=384)
# "mock"   → random unit-vector embedder (smoke test only)
# ---------------------------------------------------------------------------

EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "minilm")

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_module_dir = Path(__file__).parent

CHROMA_PERSIST_DIR: str = os.environ.get(
    "CHROMA_PERSIST_DIR", str(_module_dir / "chroma_db")
)
SQLITE_DB_PATH: str = os.environ.get(
    "SQLITE_DB_PATH", str(_module_dir / "memory.db")
)

CHROMA_COLLECTION_NAME: str = "memories"

# ---------------------------------------------------------------------------
# Pipeline tuning — all configurable, no magic numbers in business code
# ---------------------------------------------------------------------------

RECENT_TURNS_WINDOW: int = int(os.environ.get("RECENT_TURNS_WINDOW", "3"))
RETRIEVAL_TOP_K: int = int(os.environ.get("RETRIEVAL_TOP_K", "3"))

# Dedup: cosine similarity >= threshold triggers LLM judgment.
# Default 0.90 is a reasonable starting point but NOT a universal constant.
# Tune based on your embedding model and domain corpus.
DEDUP_SIMILARITY_THRESHOLD: float = float(
    os.environ.get("DEDUP_SIMILARITY_THRESHOLD", "0.90")
)

# ---------------------------------------------------------------------------
# Token budget (approximate: 1 token ≈ 4 chars)
# ---------------------------------------------------------------------------

TOKEN_BUDGET_SYSTEM: int = int(os.environ.get("TOKEN_BUDGET_SYSTEM", "200"))
TOKEN_BUDGET_RECENT: int = int(os.environ.get("TOKEN_BUDGET_RECENT", "800"))
TOKEN_BUDGET_HISTORICAL: int = int(os.environ.get("TOKEN_BUDGET_HISTORICAL", "600"))
