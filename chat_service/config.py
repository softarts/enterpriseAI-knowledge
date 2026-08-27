"""
Configuration for chat_service, resolved from environment variables.

The Hugging Face token is read ONLY from the environment (HF_TOKEN). It is
never hardcoded here and never sent to the frontend.

Environment Variables:
    HF_TOKEN            - Hugging Face access token (required to call the LLM).
    CHAT_MODEL          - HF model id (default: openai/gpt-oss-120b).
    CHAT_MAX_TOKENS     - Max tokens for the LLM response (default: 512).
    CHAT_HOST           - Bind address for the API (default: 0.0.0.0).
    CHAT_PORT           - Port for the API (default: 8100).
    CHAT_CORS_ORIGINS   - Comma-separated allowed origins for CORS
                          (default: http://localhost:5173,http://127.0.0.1:5173).
"""

import os
from typing import List


class Settings:
    """Application settings resolved from environment variables."""

    def __init__(self) -> None:
        # HF_TOKEN is intentionally read lazily at call time (see hf_client),
        # but we expose a helper here for a single source of truth.
        self.model: str = os.environ.get("CHAT_MODEL", "openai/gpt-oss-120b")
        self.max_tokens: int = int(os.environ.get("CHAT_MAX_TOKENS", "512"))
        self.host: str = os.environ.get("CHAT_HOST", "0.0.0.0")
        self.port: int = int(os.environ.get("CHAT_PORT", "8100"))
        self.service_name: str = "chat-service"
        self.version: str = "0.1.0"

        origins = os.environ.get(
            "CHAT_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
        self.cors_origins: List[str] = [
            o.strip() for o in origins.split(",") if o.strip()
        ]

    @staticmethod
    def hf_token() -> str:
        """Return the HF token from the environment, or "" if unset."""
        return os.environ.get("HF_TOKEN", "")


# Singleton instance
settings = Settings()
