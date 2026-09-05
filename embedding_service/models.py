from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class EmbeddedChunk:
    chunk_id: str
    document_id: str
    title: str
    heading: Optional[str]
    content: str
    source_path: str
    embedding: List[float]
    version: Optional[str] = None
    chunk_index: int = 0
    heading_path: Tuple[str, ...] = field(default_factory=tuple)
    content_hash: str = ""
    token_count: int = 0
    chunk_version: str = "v1"
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    normalized: Optional[bool] = None
    offsets: Optional[Tuple[int, int]] = None
    document_metadata: Dict[str, Any] = field(default_factory=dict)
