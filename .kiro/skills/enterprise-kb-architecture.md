---
inclusion: manual
---

# Enterprise Knowledge Base POC - System Architecture

This skill provides the overall system architecture for the Enterprise Knowledge Base POC project.

## Architecture Reference

The canonical architecture document is:

#[[file:enterprise_kb_poc_system_architecture.md]]

## Key Architecture Principles

1. Seven-layer architecture: Input → OKF Standardization → Vectorization → Retrieval/RAG → FastAPI → MCP → Kiro Agent
2. OKF is the knowledge intermediate layer — all downstream systems depend on OKF, not raw documents.
3. Metadata and Vector are separated concerns.
4. Retriever and LLM are decoupled — search can be verified independently from generation.
5. MCP and Knowledge Service are decoupled — MCP calls FastAPI, not internal components directly.
6. Abstract interfaces for all major components (VectorStore, Retriever, EmbeddingProvider, LLM Provider).
7. POC prioritizes FAISS locally; production migrates to Milvus via interface swap.
8. Source citation is required from day one.

## Current Implementation Status

### Completed (Layer 1, 2, 3)
- `import_raw_doc_to_okf.py`: Raw document → OKF conversion (PDF, DOCX, HTML, TXT)
- `doc_to_okf_config.yaml`: Configuration for document ingestion
- `generated/`: OKF output directory (YAML frontmatter + Markdown body, `.yaml` extension)
- `embedding_service/`: OKF → Chunks → Local Embeddings → `embedding/` persistence (mirrored JSONs)
  - `main_import.py`: Batch OKF importer (input is `generated/`, raw document direct reading is prohibited)
  - Metadata fields: title, author, created_at, tags, source_path, document_id, chunk_id

### In Progress / Next Phases
- Layer 4: Retrieval / RAG (Hybrid search, reranking)
- Layer 5: FastAPI API Service
- Layer 6: MCP Server
- Layer 7: Kiro Agent integration

## OKF File Format (Actual)

Files are stored in `./generated/` with `.yaml` extension. Format:

```yaml
---
title: <document title>
author: <author or "unknown">
created_at: '<ISO timestamp>'
tags:
- <tag1>
- <tag2>
source_path: <relative path to original source file>
---

# Document Title

<Markdown body content>
```

Note: Despite the `.yaml` extension, files contain YAML frontmatter + Markdown body (not pure YAML).

## Recommended API Project Structure (from architecture doc)

```
src/
├── api/
│   ├── main.py
│   ├── routes_documents.py
│   ├── routes_search.py
│   └── routes_query.py
├── services/
│   ├── document_service.py
│   ├── search_service.py
│   └── rag_service.py
└── retrieval/
    ├── retriever.py
    └── vector_store.py
```

## API Endpoints (Target)

| Endpoint | Method | Description | Phase |
|---|---|---|---|
| /health | GET | Service health check | Current |
| /documents | GET | List all documents | Current |
| /documents/{document_id} | GET | Get single document | Current |
| /search | GET | Search documents | Current |
| /query | POST | RAG-based Q&A | Future (requires LLM) |

## Layered Responsibility

- API Router: HTTP protocol, request/response serialization
- Service Layer: Business logic orchestration
- Repository: Data access (OKF files, future: DB, Vector Store)
- Retriever: Search abstraction (Keyword → Vector → Hybrid)
