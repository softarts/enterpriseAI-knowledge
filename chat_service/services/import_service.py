"""
Document Import orchestration (MVP: single file, synchronous).

Pipeline for one uploaded file:

    upload bytes
      -> save to temp storage (original file, as-is)
      -> extract text (reuse import_raw_doc_to_okf parsers)
      -> classify (reuse TaxonomyClassifier.classify_text)
      -> persist metadata row (state=pending)
      -> return result

    confirm:
      -> move temp file into permanent sharded storage
      -> update row (state=imported)

Deliberately NOT done here (per scope): OKF conversion, chunking, ChromaDB,
search, async jobs, auth, manual re-classification.

The document text is only used as classifier input; the ORIGINAL file is stored
unchanged.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from pathlib import Path
from typing import Any, Dict, Optional

from chat_service.config import settings
from chat_service.import_db import (
    CLS_CLASSIFIED,
    CLS_UNKNOWN,
    ImportDB,
    SRC_AUTOMATIC,
    STATE_IMPORTED,
    STATE_PENDING,
)
from chat_service.import_storage import ImportStorage, sanitize_filename

log = logging.getLogger("chat_import")


class ImportError_(Exception):
    """Domain error with a stable machine code for the API layer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# Classifier statuses that count as a usable classification.
_CLASSIFIED_RAW = {"ASSIGNED", "PARTIAL", "FALLBACK"}


class ImportService:
    """Synchronous single-file import orchestration.

    Heavy dependencies (parsers, the TaxonomyClassifier + its bge-m3 model) are
    loaded LAZILY on first use so importing this module / booting chat_service
    (and the /api/chat path) stays light.
    """

    def __init__(self) -> None:
        self.db = ImportDB(settings.import_db_path)
        self.storage = ImportStorage(settings.import_storage_dir, settings.import_temp_dir)
        self._classifier = None  # lazy TaxonomyClassifier singleton

    # ------------------------------------------------------------------
    # lazy heavy deps
    # ------------------------------------------------------------------
    def _get_classifier(self):
        if self._classifier is None:
            log.info("[import] constructing TaxonomyClassifier (first use) ...")
            from kb_classifier.taxonomy_classifier.classify import (
                PINNED_TAXONOMY_VERSION,
                TaxonomyClassifier,
            )
            self._classifier = TaxonomyClassifier()
            self._taxonomy_version = f"v{PINNED_TAXONOMY_VERSION}"
            log.info("[import] TaxonomyClassifier ready (taxonomy=%s)",
                     self._taxonomy_version)
        return self._classifier

    @staticmethod
    def _extract_text(temp_path: Path):
        """Reuse the existing parsers. Returns (title, body). Raises ImportError_."""
        from import_raw_doc_to_okf import (
            detect_file_type,
            extract_text,
            extract_title,
        )

        file_type = detect_file_type(temp_path)
        if file_type is None:
            raise ImportError_("PARSING_FAILED",
                               f"unsupported file type: {temp_path.suffix}")
        try:
            text = extract_text(temp_path, file_type)
        except ImportError as exc:  # missing optional parser lib (pdfplumber, ...)
            raise ImportError_("PARSING_FAILED",
                               f"parser dependency missing: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - any parse failure
            raise ImportError_("PARSING_FAILED", f"could not read document: {exc}") from exc

        if not text or not text.strip():
            raise ImportError_("PARSING_FAILED", "document has no extractable text")
        title = extract_title(text, temp_path)
        return title, text

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def import_file(self, original_filename: str, data: bytes) -> Dict[str, Any]:
        """Handle a single uploaded file end-to-end up to (not including) confirm.

        Returns the persisted record dict (state=pending).
        Raises ImportError_ with a stable code on any failure.
        """
        # --- validate ---
        if not data:
            raise ImportError_("UPLOAD_FAILED", "empty upload")
        if len(data) > settings.import_max_bytes:
            raise ImportError_(
                "UPLOAD_FAILED",
                f"file exceeds max size of {settings.import_max_bytes // (1024*1024)} MB",
            )
        ext = Path(sanitize_filename(original_filename)).suffix.lower()
        if ext not in settings.import_allowed_extensions:
            raise ImportError_("UPLOAD_FAILED", f"unsupported file extension: {ext or '(none)'}")

        doc_id = str(uuid_lib.uuid4())

        # --- save original to temp storage (as-is) ---
        try:
            temp_path, safe_name = self.storage.save_temp(doc_id, original_filename, data)
        except Exception as exc:  # noqa: BLE001
            raise ImportError_("STORAGE_FAILED", f"could not save upload: {exc}") from exc

        # --- parse + classify ---
        try:
            title, body = self._extract_text(temp_path)

            classifier = self._get_classifier()  # may raise on model/config problems
            try:
                cl = classifier.classify_text(title, body)
            except Exception as exc:  # noqa: BLE001
                raise ImportError_("CLASSIFICATION_FAILED",
                                   f"classification failed: {exc}") from exc

            md = cl.to_okf_metadata()
            names = md.get("category_path_names") or []
            simplified = CLS_CLASSIFIED if md.get("classification_status") in _CLASSIFIED_RAW else CLS_UNKNOWN

            record = {
                "id": doc_id,
                "original_filename": safe_name,
                "storage_path": None,  # set on confirm
                "import_state": STATE_PENDING,
                "taxonomy_version": getattr(self, "_taxonomy_version", None),
                "category_level_1": names[0] if len(names) >= 1 else None,
                "category_level_2": names[1] if len(names) >= 2 else None,
                "category_level_3": names[2] if len(names) >= 3 else None,
                "classification_status": simplified,
                "classification_source": SRC_AUTOMATIC,
                "raw_status": md.get("classification_status"),
            }
            self.db.insert(record)
            log.info("[import] pending id=%s status=%s raw=%s path=%r",
                     doc_id, simplified, record["raw_status"], md.get("category_breadcrumb"))
            return self.db.get(doc_id)
        except ImportError_:
            # Clean up the temp file we wrote, then re-raise for the API layer.
            self.storage.cleanup_temp(doc_id, safe_name)
            raise
        except Exception as exc:  # noqa: BLE001 - unexpected
            self.storage.cleanup_temp(doc_id, safe_name)
            raise ImportError_("CLASSIFICATION_FAILED", f"import failed: {exc}") from exc

    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return self.db.get(doc_id)

    def confirm(self, doc_id: str) -> Dict[str, Any]:
        """Finalize a pending import: move the file into permanent storage.

        No classification changes (scope: confirm-to-proceed only).
        Raises ImportError_ on invalid state / missing file.
        """
        rec = self.db.get(doc_id)
        if rec is None:
            raise ImportError_("NOT_FOUND", f"import '{doc_id}' not found")
        if rec["import_state"] == STATE_IMPORTED:
            raise ImportError_("CONFIRMATION_FAILED", "document already imported")
        if rec["import_state"] != STATE_PENDING:
            raise ImportError_("CONFIRMATION_FAILED",
                               f"cannot confirm from state '{rec['import_state']}'")

        try:
            storage_path = self.storage.finalize(doc_id, rec["original_filename"])
        except FileNotFoundError as exc:
            raise ImportError_("CONFIRMATION_FAILED", "pending file no longer exists") from exc
        except Exception as exc:  # noqa: BLE001
            raise ImportError_("STORAGE_FAILED", f"could not finalize storage: {exc}") from exc

        self.db.update(doc_id, {
            "storage_path": storage_path,
            "import_state": STATE_IMPORTED,
        })
        log.info("[import] imported id=%s -> %s", doc_id, storage_path)
        return self.db.get(doc_id)
