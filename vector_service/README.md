# Vector Service

`vector_service` provides the ChromaDB persistence adapter for precomputed
embeddings. The BGE-M3 import pipeline uses the model-specific collection
`okf_chunks_bge_m3`; other models use `okf_chunks_<model>`. Vectors in one
collection must have one dimension, and writes reject mixed dimensions.

Flow: `EmbeddingPipelineService` → `ChromaStore.add_embedded_chunks(...)` →
ChromaDB `upsert`; query callers provide a precomputed query vector. This
module does not extract documents, chunk Markdown, or load embedding models.

代码规模：约 384 行（vector_service Python 文件，包含 CLI、Chroma adapter、配置和注释）。
