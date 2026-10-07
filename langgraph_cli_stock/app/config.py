"""Configuration module for the application."""

import os
from pathlib import Path

# Default user ID
DEFAULT_USER_ID = "1234"

# Log directory
LOG_DIR = Path(__file__).parent.parent / "logs"

# Required environment variables
REQUIRED_ENV_VARS = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"]


def get_user_id() -> str:
    """Get user ID from command line argument or default."""
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--user-id", type=str, default=None)
    args, _ = parser.parse_known_args()
    return args.user_id if args.user_id else DEFAULT_USER_ID


def get_llm_config() -> dict:
    """Get LLM configuration from environment variables."""
    missing = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    return {
        "api_key": os.environ.get("LLM_API_KEY"),
        "base_url": os.environ.get("LLM_BASE_URL"),
        "model": os.environ.get("LLM_MODEL"),
    }


def get_log_dir() -> Path:
    """Get log directory path."""
    LOG_DIR.mkdir(exist_ok=True, parents=True)
    return LOG_DIR