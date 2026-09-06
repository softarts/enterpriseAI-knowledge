"""Conversion primitives exposed independently from the CLI."""

from pathlib import Path
from typing import Any, Dict

# The legacy script remains a compatibility CLI during this migration.  The
# public ownership and service API now live in document_import; this import can
# be removed once downstream callers have migrated.
from .legacy_converter import (
    build_metadata,
    detect_file_type,
    extract_text,
    extract_title,
    generate_okf,
    load_config,
    normalize_txt_structure,
)


def convert_path(file_path: Path, input_root: Path, config: Dict[str, Any], mirror: bool = True) -> str:
    """Read one source file and return its complete OKF representation."""
    file_type = detect_file_type(file_path)
    if file_type is None:
        raise ValueError(f"unsupported file type: {file_path.suffix}")
    text = extract_text(file_path, file_type)
    if not text.strip():
        raise ValueError("document has no extractable text")
    if file_type == "text":
        text = normalize_txt_structure(text)
    relative = file_path.relative_to(input_root) if mirror and file_path.is_relative_to(input_root) else Path(file_path.name)
    document_id = relative.with_suffix("").as_posix().replace("/", "-").replace("_", "-").lower()
    metadata = build_metadata(file_path, text, config, input_root, document_id, file_type)
    return generate_okf(text, metadata)
