"""Chat model configuration for the short-term memory graph."""

from __future__ import annotations

import os
from typing import Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY") or ""
OPENAI_BASE_URL: Optional[str] = (
    os.environ.get("OPENAI_BASE_URL") or os.environ.get("LLM_BASE_URL") or None
)
MODEL_NAME: str = (
    os.environ.get("MODEL_NAME") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
)


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
