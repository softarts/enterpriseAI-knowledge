"""HTTP server and CORS configuration for chat_service."""

from __future__ import annotations

import os
from typing import List


class Settings:
    """Non-LLM settings retained for application startup and API health."""

    def __init__(self) -> None:
        self.host: str = os.environ.get("CHAT_HOST", "0.0.0.0")
        self.port: int = int(os.environ.get("CHAT_PORT", "8100"))
        self.service_name: str = "chat-service"
        self.version: str = "0.1.0"
        origins = os.environ.get(
            "CHAT_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
        self.cors_origins: List[str] = [
            origin.strip() for origin in origins.split(",") if origin.strip()
        ]


settings = Settings()
