"""
Application configuration loaded from environment variables.

Environment Variables:
    KB_OKF_DIR   - Path to the OKF documents directory (default: ./generated)
    KB_HOST      - API server host (default: 0.0.0.0)
    KB_PORT      - API server port (default: 8000)
    KB_MCP_PORT  - MCP server port (default: 8001)
"""

import os
from pathlib import Path


class Settings:
    """Application settings resolved from environment variables."""

    def __init__(self) -> None:
        self.okf_dir: Path = Path(
            os.environ.get("KB_OKF_DIR", "./generated")
        ).resolve()
        self.host: str = os.environ.get("KB_HOST", "0.0.0.0")
        self.port: int = int(os.environ.get("KB_PORT", "8000"))
        self.mcp_port: int = int(os.environ.get("KB_MCP_PORT", "8001"))
        self.service_name: str = "enterprise-kb-api"
        self.version: str = "0.1.0"


# Singleton instance
settings = Settings()
