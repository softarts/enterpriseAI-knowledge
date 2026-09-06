"""Model-neutral embedding service configuration."""

import os
from pathlib import Path
from typing import Any, Dict

ACTIVE_MODEL = os.getenv("EMBEDDING_MODEL", "bge_m3")
BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
DEFAULT_OKF_DIR = Path(os.getenv("EMBEDDING_OKF_DIR", "generated"))
DEFAULT_EMBEDDING_DIR = Path(os.getenv("EMBEDDING_DIR", "embedding"))
CHUNK_TARGET_TOKENS = 700
CHUNK_MIN_TOKENS = 150
CHUNK_MAX_TOKENS = 1100
CHUNK_OVERLAP_RATIO = 0.12


def model_config(name: str) -> Dict[str, Any]:
    from embedding_service.models_registry import get_model_config
    return get_model_config(name)


# Compatibility names for callers that used the old module constants. They
# describe the active configured model; model implementations own their values.
EMBEDDING_MODEL_NAME = model_config(ACTIVE_MODEL)["model_name"]
EMBEDDING_DIMENSION = model_config(ACTIVE_MODEL)["dimension"]
