"""
memory_system.llm.client — LLM client abstraction.

Two implementations:
    OpenAILLMClient  — real OpenAI-compatible API (plain openai package)
    MockLLMClient    — deterministic responses for smoke tests

Usage:
    from memory_system.llm.client import get_llm_client
    client = get_llm_client()
    result = client.chat_json(system_prompt, user_prompt)

All LLM calls return structured JSON. The caller is responsible for
parsing the JSON into the appropriate output schema.
"""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract LLM client. All calls return parsed JSON dict."""

    @abstractmethod
    def chat_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        Send a chat completion request and return a parsed JSON dict.

        Args:
            system_prompt: The system instruction (includes JSON schema).
            user_prompt:   The user message.

        Returns:
            Parsed JSON response as a dict.
        """
        ...


class OpenAILLMClient(LLMClient):
    """
    Production LLM client using the plain openai package.

    Connects to any OpenAI-compatible endpoint (OpenRouter, LM Studio, etc.)
    via environment variables:
        LLM_BASE_URL, LLM_MODEL, LLM_API_KEY, LLM_MAX_TOKENS
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        max_tokens: int = 2048,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "openai is required. Install with: pip install openai"
            ) from exc

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens
        logger.info("OpenAILLMClient initialised: model=%s base_url=%s", model, base_url)

    def chat_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        Call LLM with JSON output mode.

        Falls back to prompt-based JSON extraction if the endpoint does not
        support response_format (e.g., some OpenRouter free models).
        """
        logger.debug(
            "LLM call: system_len=%d user_len=%d model=%s",
            len(system_prompt),
            len(user_prompt),
            self._model,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=self._max_tokens,
                temperature=0,
                response_format={"type": "json_object"},
            )
        except Exception:
            # Some providers do not support response_format; fall back
            logger.debug("response_format not supported, falling back to plain call")
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=self._max_tokens,
                temperature=0,
            )

        raw = response.choices[0].message.content or ""
        logger.debug("LLM raw response: %s", raw[:300])
        return _parse_json(raw)


class MockLLMClient(LLMClient):
    """
    Mock LLM client for smoke tests and local development without API access.

    Returns deterministic, realistic responses based on keyword detection
    in the user prompt. Clearly NOT for production use.
    """

    def chat_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        prompt_lower = (system_prompt + " " + user_prompt).lower()
        logger.debug("MockLLMClient.chat_json called (smoke test mode)")

        # ---- Query rewrite ----
        if "rewritten_query" in prompt_lower:
            # Extract just the current query portion from the prompt
            current_query = user_prompt
            if "Current query:" in user_prompt:
                current_query = user_prompt.split("Current query:")[-1].strip()
            return {"rewritten_query": current_query}

        # ---- Memory extraction ----
        if "should_store" in prompt_lower:
            low = user_prompt.lower()
            # Skip trivial turns
            trivial = any(
                t in low
                for t in ["hello", "hi ", "thanks", "thank you", "好的", "明白", "谢谢", "ok", "okay"]
            )
            if trivial and len(user_prompt) < 30:
                return {"should_store": False, "content": ""}
            # Generate a simple content summary
            content = _mock_memory_content(user_prompt)
            return {"should_store": True, "content": content}

        # ---- Dedup judgment ----
        if "decision" in prompt_lower or "duplicate" in prompt_lower or "dedup" in prompt_lower:
            return {"decision": "distinct"}

        # ---- Answer generation (fallback) ----
        return {"answer": f"[Mock answer for: {user_prompt[:80]}]"}


def _mock_memory_content(text: str) -> str:
    """Generate a simple memory content string for mock mode."""
    text = text.strip()
    if len(text) > 80:
        text = text[:80] + "..."
    if not text.endswith("。") and not text.endswith("."):
        text = text + " 的相关内容与规定"
    return text


def _parse_json(raw: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM output, handling markdown fences and leading text.
    """
    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Extract first {...} block
    brace_match = re.search(r"\{[\s\S]*\}", raw)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from LLM response: %s", raw[:200])
    return {}


def get_llm_client() -> LLMClient:
    """
    Factory: returns OpenAILLMClient if env vars are set, else MockLLMClient.

    MockLLMClient is returned automatically when LLM_BASE_URL or LLM_API_KEY
    are not configured. This enables pipeline smoke tests without API access.
    """
    from memory_system import config

    if config.LLM_BASE_URL and config.LLM_API_KEY and config.LLM_MODEL:
        return OpenAILLMClient(
            base_url=config.LLM_BASE_URL,
            model=config.LLM_MODEL,
            api_key=config.LLM_API_KEY,
            max_tokens=config.LLM_MAX_TOKENS,
        )
    logger.warning(
        "LLM env vars not fully set (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL). "
        "Using MockLLMClient — NOT suitable for production."
    )
    return MockLLMClient()
