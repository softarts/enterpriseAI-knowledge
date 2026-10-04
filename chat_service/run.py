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
import logging.handlers
import os

import uvicorn
from chat_service.services.chat.config import settings
from qa_service import config as qa_config

# Repo-root logs/ dir, regardless of the process's cwd. Rotating so a long-
# running dev server doesn't grow this file unbounded. Every INFO+ log line
# (including the per-call `call_trace` entries from langchain_agent/app/
# call_trace.py) lands here as well as on the console, so a failed turn can
# be analyzed straight from the file instead of only from whatever scrollback
# the terminal still has.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_LOG_DIR = os.path.join(_REPO_ROOT, "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(_LOG_DIR, "chat_service.log")

_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)
_file_handler = logging.handlers.RotatingFileHandler(
    _LOG_FILE, maxBytes=20 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(_formatter)
logging.basicConfig(level=logging.INFO, handlers=[_console_handler, _file_handler])
logger = logging.getLogger(__name__)
logger.info("Logging to console and %s", _LOG_FILE)


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
