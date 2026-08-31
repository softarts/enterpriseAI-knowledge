"""
File storage for the Document Import feature (MVP).

The original uploaded file is stored AS-IS (no OKF conversion). Layout uses a
fixed 256-way shard derived from the document UUID so no single directory grows
unbounded, and taxonomy never influences the path (re-classifying never moves a
file):

    storage/documents/{shard}/{uuid}_{safe_original_filename}

where shard = int(md5(uuid)) % 256, zero-padded to 3 digits.

Two roots are used:
    temp_dir     - pending uploads awaiting confirmation
    storage_dir  - permanent storage after confirm

Security:
    * The user-provided filename never controls the directory. We sanitize it to
      a bare basename and strip anything unsafe; the directory is decided solely
      by the server-generated UUID.
    * All resolved paths are asserted to stay within their root (defense in depth
      against path traversal).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Optional

# Characters allowed in a stored filename; everything else becomes "_".
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._ \-()]+")


def sanitize_filename(name: str) -> str:
    """Reduce an arbitrary user filename to a safe bare basename.

    Strips any path components and disallowed characters. Never returns an empty
    string or a name that could traverse directories.
    """
    # Take basename only — kill any directory components (both separators).
    base = os.path.basename(name.replace("\\", "/")).strip()
    base = _SAFE_CHARS.sub("_", base)
    base = base.strip(" .")  # no leading/trailing dots or spaces (Windows-safe)
    return base or "file"


def shard_for(uuid: str) -> str:
    """Deterministic 3-digit shard directory name for a UUID (000..255)."""
    digest = hashlib.md5(uuid.encode("utf-8")).hexdigest()
    return f"{int(digest, 16) % 256:03d}"


def _relative_storage_path(uuid: str, safe_filename: str) -> Path:
    """documents/{shard}/{uuid}_{safe_filename} (relative to a root)."""
    return Path("documents") / shard_for(uuid) / f"{uuid}_{safe_filename}"


def _assert_within(root: Path, target: Path) -> Path:
    """Return the resolved target, guaranteeing it stays inside root."""
    root_r = root.resolve()
    target_r = target.resolve()
    if os.path.commonpath([str(root_r), str(target_r)]) != str(root_r):
        raise ValueError("resolved path escapes its storage root")
    return target_r


class ImportStorage:
    """Temp + permanent file storage with UUID sharding."""

    def __init__(self, storage_dir: Path, temp_dir: Path) -> None:
        self.storage_dir = Path(storage_dir)
        self.temp_dir = Path(temp_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def temp_path(self, uuid: str, safe_filename: str) -> Path:
        """Absolute temp path for a pending upload (mirrors final layout)."""
        rel = _relative_storage_path(uuid, safe_filename)
        target = self.temp_dir / rel
        return _assert_within(self.temp_dir, target)

    def save_temp(self, uuid: str, original_filename: str, data: bytes) -> tuple[Path, str]:
        """Write the upload bytes to temp storage.

        Returns (absolute_temp_path, safe_filename).
        """
        safe = sanitize_filename(original_filename)
        target = self.temp_path(uuid, safe)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(data)
        return target, safe

    def finalize(self, uuid: str, safe_filename: str) -> str:
        """Move a pending temp file into permanent storage.

        Returns the storage_path RELATIVE to storage_dir (stored in the DB).
        """
        rel = _relative_storage_path(uuid, safe_filename)
        src = _assert_within(self.temp_dir, self.temp_dir / rel)
        dst = _assert_within(self.storage_dir, self.storage_dir / rel)
        if not src.exists():
            raise FileNotFoundError(f"pending file missing for id {uuid}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return str(rel).replace("\\", "/")

    def cleanup_temp(self, uuid: str, safe_filename: str) -> None:
        """Best-effort removal of a pending temp file (cancel / failure paths)."""
        try:
            rel = _relative_storage_path(uuid, safe_filename)
            src = self.temp_dir / rel
            if src.exists():
                src.unlink()
        except OSError:
            pass

    def storage_exists(self, storage_path: str) -> bool:
        """Whether a finalized relative storage_path exists on disk."""
        if not storage_path:
            return False
        return (self.storage_dir / storage_path).exists()
