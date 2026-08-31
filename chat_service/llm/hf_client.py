"""
Thin wrapper around Hugging Face Cloud Inference.

Uses the exact pattern already verified for this project:
    - token from env var HF_TOKEN
    - huggingface_hub.InferenceClient(api_key=token, provider="auto")
    - model openai/gpt-oss-120b
    - client.chat.completions.create(...)

The token is read from the environment only; it is never logged, hardcoded,
or returned to the frontend.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from huggingface_hub import InferenceClient

from chat_service.config import settings


class HFTokenMissingError(RuntimeError):
    """Raised when HF_TOKEN is not present in the environment."""


class HuggingFaceLLM:
    """Minimal chat-completions client for a single HF model."""

    def __init__(self, model: str | None = None, max_tokens: int | None = None) -> None:
        self.model = model or settings.model
        self.max_tokens = max_tokens or settings.max_tokens

    def _client(self) -> InferenceClient:
        token = settings.hf_token()
        if not token:
            raise HFTokenMissingError(
                "HF_TOKEN environment variable is not set. Export a valid "
                "Hugging Face token before starting chat_service."
            )
        return InferenceClient(api_key=token, provider="auto")

    def chat(self, question: str) -> Dict[str, Any]:
        """
        Send a single user message and return the answer plus lightweight
        metadata for the trace.

        Returns:
            {
              "answer": str,
              "model": str,
              "max_tokens": int,
              "finish_reason": str | None,
              "usage": dict | None,
            }

        Raises:
            HFTokenMissingError: if HF_TOKEN is unset.
            Exception: any error raised by the HF client is propagated to the
                       caller so it can be recorded in the trace.
        """
        client = self._client()
        messages: List[Dict[str, str]] = [{"role": "user", "content": question}]

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
        )

        choice = response.choices[0]
        answer = choice.message.content or ""

        usage = None
        raw_usage = getattr(response, "usage", None)
        if raw_usage is not None:
            # usage may be a pydantic-like object; coerce to a plain dict.
            usage = {
                "prompt_tokens": getattr(raw_usage, "prompt_tokens", None),
                "completion_tokens": getattr(raw_usage, "completion_tokens", None),
                "total_tokens": getattr(raw_usage, "total_tokens", None),
            }

        return {
            "answer": answer,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "finish_reason": getattr(choice, "finish_reason", None),
            "usage": usage,
        }
