"""
Run the chat_service API with uvicorn.

Usage:
    python -m chat_service.run

Environment:
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL - shared OpenAI-compatible LLM settings
    CHAT_HOST   - default 0.0.0.0
    CHAT_PORT   - default 8100
"""

import logging

import uvicorn
import os
from chat_service.services.chat.config import settings
from qa_service import config as qa_config

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
    logger.info("Model: %s", qa_config.LLM_MODEL)
    logger.info("LLM_API_KEY configured: %s", bool(qa_config.LLM_API_KEY))
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
