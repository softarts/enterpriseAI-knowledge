"""Small registry: selection lives here; model behavior lives in model packages."""

from typing import Any, Dict, Optional

_MODEL_CONFIGS = {
    "bge_m3": {"model_name": "BAAI/bge-m3", "dimension": 1024, "normalize_embeddings": True},
    "minilm": {"model_name": "all-MiniLM-L6-v2", "dimension": 384, "normalize_embeddings": True},
}


def get_model_config(name: str) -> Dict[str, Any]:
    try:
        return dict(_MODEL_CONFIGS[name])
    except KeyError as exc:
        raise ValueError(f"Unknown embedding model: {name!r}; available: {sorted(_MODEL_CONFIGS)}") from exc


def create_embedder(name: Optional[str] = None, **overrides: object):
    from embedding_service.config import ACTIVE_MODEL
    selected = name or ACTIVE_MODEL
    config = get_model_config(selected)
    config.update(overrides)
    if selected == "bge_m3":
        from embedding_service.bge_m3.embedder import BgeM3Embedder
        return BgeM3Embedder(**config)
    if selected == "minilm":
        from embedding_service.minilm.embedder import MiniLMEmbedder
        return MiniLMEmbedder(**config)
    raise ValueError(f"Unknown embedding model: {selected!r}")
