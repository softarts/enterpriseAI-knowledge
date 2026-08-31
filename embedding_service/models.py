from dataclasses import dataclass
from typing import List, Optional


@dataclass
class EmbeddedChunk:
    """
    Metadata and embedding representation of an OKF chunk.
    """
    chunk_id: str
    document_id: str
    title: str
    heading: Optional[str]
    content: str
    source_path: str
    embedding: List[float]
