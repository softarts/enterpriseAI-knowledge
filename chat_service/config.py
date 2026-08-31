"""
Configuration for chat_service.

Non-secret LLM settings (provider, model, max_tokens) and the *reference* to the
token live in a config file: chat_service/llm_config.yaml. The api_key entry in
that file is an environment-variable REFERENCE (e.g. ${HF_TOKEN}), never a
literal token, so no secret is ever committed to the repo.

Resolution order (highest priority first):
    1. Environment variables (CHAT_MODEL, CHAT_MAX_TOKENS, ...) — runtime override.
    2. llm_config.yaml values (with ${VAR} placeholders resolved from the env).
    3. Built-in defaults.

The Hugging Face token itself is always read from the environment. The YAML only
says WHICH env var holds it (api_key: ${HF_TOKEN}); it never stores the value.

Environment Variables:
    HF_TOKEN            - Hugging Face access token (required to call the LLM).
    CHAT_MODEL          - Override the model id from the config file.
    CHAT_MAX_TOKENS     - Override max response tokens from the config file.
    CHAT_LLM_CONFIG     - Path to the LLM config file (default: llm_config.yaml).
    CHAT_HOST           - Bind address for the API (default: 0.0.0.0).
    CHAT_PORT           - Port for the API (default: 8100).
    CHAT_CORS_ORIGINS   - Comma-separated allowed origins for CORS
                          (default: http://localhost:5173,http://127.0.0.1:5173).
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

_ENV_REF_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

DEFAULT_LLM_CONFIG_PATH = Path(__file__).resolve().parent / "llm_config.yaml"


def _resolve_env_refs(value: Any) -> Any:
    """
    Replace ${VAR} references in strings with the corresponding environment
    variable value. Non-string values pass through unchanged. If the referenced
    env var is unset, the placeholder resolves to an empty string.
    """
    if isinstance(value, str):
        return _ENV_REF_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), ""), value
        )
    return value


def _load_llm_config() -> Dict[str, Any]:
    """Load llm_config.yaml (if present) and resolve ${VAR} references."""
    path = Path(os.environ.get("CHAT_LLM_CONFIG", str(DEFAULT_LLM_CONFIG_PATH)))
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return {k: _resolve_env_refs(v) for k, v in raw.items()}


class Settings:
    """Application settings resolved from the LLM config file + environment."""

    def __init__(self) -> None:
        cfg = _load_llm_config()

        # Which env var holds the token. The YAML's api_key is an env reference
        # (e.g. ${HF_TOKEN}); we remember the *name* so hf_token() reads it live.
        self._token_env_var: str = self._extract_token_env_var(cfg)

        # Non-secret LLM settings: env override > config file > default.
        self.provider: str = cfg.get("provider", "huggingface")
        self.model: str = os.environ.get(
            "CHAT_MODEL", cfg.get("model", "openai/gpt-oss-120b")
        )
        self.max_tokens: int = int(
            os.environ.get("CHAT_MAX_TOKENS", cfg.get("max_tokens", 512))
        )

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
    def _extract_token_env_var(cfg: Dict[str, Any]) -> str:
        """
        Determine which environment variable holds the token, based on the
        RAW ${VAR} reference in the config file. Falls back to HF_TOKEN.
        """
        path = Path(os.environ.get("CHAT_LLM_CONFIG", str(DEFAULT_LLM_CONFIG_PATH)))
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            api_key_ref = raw.get("api_key", "")
            match = _ENV_REF_PATTERN.fullmatch(str(api_key_ref).strip())
            if match:
                return match.group(1)
        return "HF_TOKEN"

    def hf_token(self) -> str:
        """
        Return the token from the environment variable named by the config's
        api_key reference (default HF_TOKEN), or "" if unset. The token value is
        never stored on this object.
        """
        return os.environ.get(self._token_env_var, "")


# Singleton instance
settings = Settings()
