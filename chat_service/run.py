"""
Run the chat_service API with uvicorn.

Usage:
    python -m chat_service.run

Environment:
    HF_TOKEN    - required for legacy direct-chat calls (see chat_service/service/chat/config.py)
    CHAT_HOST   - default 0.0.0.0
    CHAT_PORT   - default 8100
"""

import logging

import uvicorn
import os
from chat_service.services.chat.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("=" * 60)
    logger.info("Enterprise AI Playground — chat_service")
    logger.info("API: http://%s:%d", settings.host, settings.port)
    logger.info("Model: %s", settings.model)
    logger.info("HF_TOKEN configured: %s", bool(settings.hf_token()))
    logger.info("CORS origins: %s", ", ".join(settings.cors_origins))
    logger.info("=" * 60)


    llmapi = os.environ.get("LLM_BASE_URL", "dummy API")
    logger.info("LLM_BASE_URLconfigured: %s", llmapi)

    uvicorn.run(
        "chat_service.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
