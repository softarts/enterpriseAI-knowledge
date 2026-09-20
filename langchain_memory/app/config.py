"""Configuration and model integration for LangGraph Memory MVP V1."""

from __future__ import annotations

import os
import logging
from typing import Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

logger = logging.getLogger(__name__)


# Environment configuration
OPENAI_API_KEY: str = (
    os.environ.get("OPENAI_API_KEY")
    or os.environ.get("LLM_API_KEY")
    or ""
)
OPENAI_BASE_URL: Optional[str] = (
    os.environ.get("OPENAI_BASE_URL")
    or os.environ.get("LLM_BASE_URL")
    or None
)
MODEL_NAME: str = (
    os.environ.get("MODEL_NAME")
    or os.environ.get("LLM_MODEL")
    or "gpt-4o-mini"
)
EMBEDDING_MODEL: str = os.environ.get("MEMORY_EMBEDDING_MODEL", "bge_m3")
EMBEDDING_DIMS: int = int(os.environ.get("MEMORY_EMBEDDING_DIMS", "1024"))
DEFAULT_TOP_K: int = int(os.environ.get("MEMORY_TOP_K", "3"))


def get_chat_model(
    model_name: Optional[str] = None,
    temperature: float = 0.0,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> BaseChatModel:
    """Centralized factory for chat model integration."""
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


def get_embeddings(
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Embeddings:
    """Centralized factory for embedding model integration."""
    resolved_model = model_name or EMBEDDING_MODEL
    if resolved_model in {"bge_m3", "minilm"}:
        from embedding_service import get_embedder

        logger.info(
            "Creating local memory embeddings model=%s dims=%d",
            resolved_model,
            EMBEDDING_DIMS,
        )
        return get_embedder(resolved_model)

    resolved_key = api_key or OPENAI_API_KEY or "dummy-key"
    resolved_base_url = base_url or OPENAI_BASE_URL

    kwargs = {
        "model": resolved_model,
        "api_key": resolved_key,
    }
    if resolved_base_url:
        kwargs["base_url"] = resolved_base_url

    logger.info("Creating OpenAI-compatible memory embeddings model=%s", resolved_model)
    return OpenAIEmbeddings(**kwargs)

