"""Chat model and memory-embedding configuration for the memory graph."""

from __future__ import annotations

import os
from typing import List, Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY") or ""
OPENAI_BASE_URL: Optional[str] = (
    os.environ.get("OPENAI_BASE_URL") or os.environ.get("LLM_BASE_URL") or None
)
MODEL_NAME: str = (
    os.environ.get("MODEL_NAME") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
)

# Long-term memory store index configuration.
MEMORY_EMBEDDING_MODEL: str = os.environ.get("MEMORY_EMBEDDING_MODEL") or "bge_m3"
MEMORY_EMBEDDING_DIMS: int = int(os.environ.get("MEMORY_EMBEDDING_DIMS") or "1024")
MEMORY_TOP_K: int = int(os.environ.get("MEMORY_TOP_K") or "3")

# Human-in-the-loop gate: interrupt before running internet-touching tools.
HITL_ENABLED: bool = (
    os.environ.get("HITL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
)

# Local alias -> HuggingFace model name, aligned with
# embedding_service/models_registry.py so the memory index and the enterprise KB
# use the same embedding space.
_EMBEDDING_MODEL_REGISTRY = {
    "bge_m3": "BAAI/bge-m3",
}


class SentenceTransformerEmbeddings(Embeddings):
    """Minimal langchain-core Embeddings wrapper around sentence-transformers."""

    def __init__(self, model_name: str, normalize_embeddings: bool = True) -> None:
        from sentence_transformers import SentenceTransformer  # lazy heavy import

        self._model = SentenceTransformer(model_name)
        self._normalize = normalize_embeddings

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._model.encode(
            list(texts), normalize_embeddings=self._normalize
        ).tolist()

    def embed_query(self, text: str) -> List[float]:
        return self._model.encode(
            [text], normalize_embeddings=self._normalize
        )[0].tolist()


def get_embeddings(model_name: Optional[str] = None) -> Embeddings:
    """Create the embeddings used by the long-term memory store index."""
    alias = model_name or MEMORY_EMBEDDING_MODEL
    resolved = _EMBEDDING_MODEL_REGISTRY.get(alias, alias)
    return SentenceTransformerEmbeddings(model_name=resolved)


def get_chat_model(
    model_name: Optional[str] = None,
    temperature: float = 0.0,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> BaseChatModel:
    """Create the configured chat model."""
    resolved_key = api_key or OPENAI_API_KEY or "dummy-key"
    resolved_model = model_name or MODEL_NAME
    resolved_base_url = base_url or OPENAI_BASE_URL

    kwargs = {
        "model": resolved_model,
        "temperature": temperature,
        "api_key": resolved_key,
    }
    if resolved_base_url:
        kwargs["base_url"] = resolved_base_url

    return ChatOpenAI(**kwargs)
