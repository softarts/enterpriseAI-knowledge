"""
chat_service — standalone Enterprise AI Playground backend.

A minimal, self-contained FastAPI service that powers the Playground Web UI.
It is intentionally decoupled from doc_service / vector_service / MCP: the
first version only implements a direct LLM Ask flow:

    Browser -> chat_service -> Hugging Face Cloud LLM -> Answer + Trace

Future stages (RAG via vector_service.search(), BM25, reranker, agent/ReAct)
plug into ChatService without changing the public API.
"""
