"""
OKF Document Repository.

Reads OKF files (YAML frontmatter + Markdown body) from the configured
directory and exposes them as DocumentRecord domain objects.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import yaml

import doc_service.core.config as _config_module
from doc_service.domain.document import DocumentRecord

logger = logging.getLogger(__name__)

# Regex to split YAML frontmatter from Markdown body
_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL
)


class OKFDocumentRepository:
    """
    Repository that reads OKF documents from the filesystem.

    All file I/O and YAML parsing is encapsulated here.
    Service and API layers never touch files directly.
    """

    def __init__(self, okf_dir: Optional[Path] = None) -> None:
        self._okf_dir = okf_dir or _config_module.settings.okf_dir
        self._cache: Optional[Dict[str, DocumentRecord]] = None

    # ------------------------------------------------------------------
    # Public interface (satisfies DocumentRepository protocol)
    # ------------------------------------------------------------------

    def list_documents(
        self,
        keyword: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[DocumentRecord]:
        """List documents with optional keyword/tag filtering."""
        docs = list(self._get_all().values())

        if keyword:
            kw_lower = keyword.lower()
            docs = [
                d for d in docs if kw_lower in d.title.lower()
            ]

        if tag:
            tag_lower = tag.lower()
            docs = [
                d for d in docs
                if any(t.lower() == tag_lower for t in d.tags)
            ]

        return docs

    def get_document(self, document_id: str) -> Optional[DocumentRecord]:
        """Get a single document by its stable ID."""
        return self._get_all().get(document_id)

    def reload(self) -> None:
        """Force reload of documents from disk (invalidate cache)."""
        self._cache = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_all(self) -> Dict[str, DocumentRecord]:
        """Lazy-load and cache all OKF documents."""
        if self._cache is None:
            self._cache = self._scan_and_parse()
        return self._cache

    def _scan_and_parse(self) -> Dict[str, DocumentRecord]:
        """Scan the OKF directory and parse all .yaml files."""
        documents: Dict[str, DocumentRecord] = {}

        if not self._okf_dir.exists():
            logger.warning("OKF directory does not exist: %s", self._okf_dir)
            return documents

        for file_path in sorted(self._okf_dir.rglob("*.yaml")):
            try:
                record = self._parse_okf_file(file_path)
                if record:
                    documents[record.document_id] = record
            except Exception as e:
                logger.error("Failed to parse OKF file %s: %s", file_path, e)

        logger.info("Loaded %d OKF documents from %s", len(documents), self._okf_dir)
        return documents

    def _parse_okf_file(self, file_path: Path) -> Optional[DocumentRecord]:
        """Parse a single OKF file into a DocumentRecord."""
        raw = file_path.read_text(encoding="utf-8")

        match = _FRONTMATTER_RE.match(raw)
        if not match:
            logger.warning("No valid frontmatter found in %s", file_path)
            return None

        frontmatter_str = match.group(1)
        body = match.group(2).strip()

        try:
            metadata = yaml.safe_load(frontmatter_str) or {}
        except yaml.YAMLError as e:
            logger.error("YAML parse error in %s: %s", file_path, e)
            return None

        document_id = metadata.get("document_id") or self._generate_document_id(file_path)

        return DocumentRecord(
            document_id=str(document_id),
            title=metadata.get("title", ""),
            author=metadata.get("author", "unknown"),
            created_at=metadata.get("created_at"),
            tags=metadata.get("tags", []),
            source_path=metadata.get("source_path", ""),
            content=body,
            file_path=str(file_path),
        )

    def _generate_document_id(self, file_path: Path) -> str:
        """
        Generate a stable, deterministic document ID from the file path.

        Strategy:
          1. Get path relative to okf_dir
          2. Strip the .yaml extension
          3. Replace path separators and underscores with hyphens
          4. Lowercase
          5. Collapse multiple hyphens

        Example:
          generated/security/account_policy.yaml -> security-account-policy
          generated/dsid_abc__some-doc.yaml -> dsid-abc--some-doc
        """
        try:
            relative = file_path.relative_to(self._okf_dir)
        except ValueError:
            relative = Path(file_path.name)

        # Remove extension
        stem = str(relative.with_suffix(""))

        # Normalize separators
        doc_id = stem.replace("\\", "/").replace("/", "-").replace("_", "-")

        # Lowercase and collapse multiple hyphens
        doc_id = re.sub(r"-+", "-", doc_id).lower().strip("-")

        return doc_id
