"""
Vector service package (Phase 1).

Chroma-backed persistent vector store for OKF chunk embeddings. This package is
intentionally minimal: it only covers Embedding -> Chroma -> Vector Search.

No BM25, reranking, hybrid search, MCP, LLM, or context assembly here.
"""
