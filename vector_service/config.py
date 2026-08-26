"""
Vector service configuration (Phase 1).

Defaults for the Chroma persistent vector store.
"""

# Directory (relative to project root) for Chroma persistent storage.
DEFAULT_VECTOR_DB_DIR = "vector_db"

# Single collection holding all OKF chunk embeddings.
COLLECTION_NAME = "okf_chunks"

# Distance metric. Chunk embeddings are L2-normalized by the embedder, so cosine
# distance is the natural choice (cosine distance = 1 - cosine similarity).
DISTANCE_SPACE = "cosine"

# Default number of neighbors returned by a search.
DEFAULT_TOP_K = 5
