"""Shared configuration for document import and maintenance tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Set


class ImportSettings:
    def __init__(self) -> None:
        import_root = Path(os.environ.get(
            "CHAT_IMPORT_ROOT",
            str(Path(__file__).resolve().parent.parent / "import_data"),
        ))
        self.import_db_path = Path(os.environ.get("CHAT_IMPORT_DB", str(import_root / "documents.db")))
        self.import_storage_dir = Path(os.environ.get("CHAT_IMPORT_STORAGE_DIR", str(import_root / "okf")))
        self.import_temp_dir = Path(os.environ.get("CHAT_IMPORT_TEMP_DIR", str(import_root / "temp")))
        self.import_max_bytes = int(os.environ.get("CHAT_IMPORT_MAX_MB", "25")) * 1024 * 1024
        self.import_allowed_extensions: Set[str] = {
            ".pdf", ".docx", ".doc", ".html", ".htm", ".txt", ".md", ".rst",
        }


settings = ImportSettings()
