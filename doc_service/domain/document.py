"""Internal domain model for documents."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DocumentRecord:
    """
    Internal representation of a parsed OKF document.

    This is the domain model used within the service layer.
    It is NOT an API schema — conversion happens at the API boundary.
    """

    document_id: str
    title: str
    author: str
    created_at: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    source_path: str = ""
    content: str = ""
    file_path: str = ""  # Actual OKF file path on disk
