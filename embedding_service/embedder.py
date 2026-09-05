"""Compatibility-free public embedder protocol and factory entry point."""

from typing import List, Optional, Protocol, Sequence


class Embedder(Protocol):
    model_name: str
    dimension: int
    normalize_embeddings: bool

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]: ...
    def embed_query(self, text: str) -> List[float]: ...


def get_embedder(active_model: Optional[str] = None, **overrides: object) -> Embedder:
    from embedding_service.models_registry import create_embedder
    return create_embedder(active_model, **overrides)
