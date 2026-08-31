---
inclusion: manual
---

# Enterprise KB POC - API Service Layer Implementation Guide

This skill defines the requirements and constraints for implementing the FastAPI-based API Service Layer (Layer 5) that exposes existing OKF documents to external agents.

## Scope of This Phase

Implement ONLY:
- FastAPI service that reads existing OKF files from `./generated/`
- Clean layered architecture: Router → Service → Repository → OKF Files
- Simple keyword-based search (placeholder for future vector search)
- Stable document ID generation from file paths

Do NOT implement:
- Document import / parsing (already exists in `import_raw_doc_to_okf.py`)
- Embedding / Vectorization
- FAISS / Milvus / any Vector DB
- RAG / LLM integration
- MCP Server
- POST /query endpoint
- Authentication / RBAC / Multi-tenancy
- PostgreSQL / Redis / Kafka / Celery / Elasticsearch
- Docker / Kubernetes / Microservices

## Hard Constraints

1. **DO NOT modify** `import_raw_doc_to_okf.py` unless API cannot reasonably consume its output (requires explicit justification and approval).
2. **DO NOT** duplicate any Parser logic (PDF/DOCX/HTML/TXT).
3. **DO NOT** create a second OKF Converter or Metadata Builder.
4. **DO NOT** create a second config loader.
5. **DO NOT** change the format of files in `generated/`.
6. **DO NOT** modify existing CLI behavior.
7. **DO NOT** restructure existing code for API convenience.
8. The API Layer is a **consumer** of OKF output, not a producer.

## Data Source

The primary data source is the `./generated/` directory containing OKF files produced by `import_raw_doc_to_okf.py`.

### Actual OKF File Format

- Extension: `.yaml`
- Location: `./generated/` (flat or mirrored directory structure)
- Content format: YAML frontmatter + Markdown body

```yaml
---
title: <string>
author: <string>
created_at: '<ISO datetime>'
tags:
- <string>
source_path: <relative path to original source>
---

# Title

<Markdown body>
```

**Important**: The `generated/` directory does NOT have a `documents/` subdirectory in the current implementation. Files are directly in `generated/` (possibly with subdirectories mirroring source structure).

## Architecture Requirements

### Layered Design (Mandatory)

```
API Router (routes_documents.py)
    ↓
KnowledgeService
    ↓
OKFDocumentRepository
    ↓
generated/ (OKF files)
```

**Forbidden patterns:**
- Router directly reading files
- Router directly parsing YAML
- Router directly traversing `generated/`

### Document ID Strategy

- Derived from OKF file path relative to `generated/`
- Must be deterministic (same file → same ID every time)
- No random UUIDs, no startup-generated IDs, no memory-order dependent IDs
- Normalize: strip extension, replace path separators and underscores with hyphens
- Example: `security/account_policy.yaml` → `security-account-policy`
- Centralize ID generation logic in Repository / Document Identity module

### Repository Design

```python
class DocumentRepository(Protocol):
    def list_documents(...) -> ...: ...
    def get_document(document_id: str) -> ...: ...
    def search(query: str, top_k: int) -> ...: ...
```

Current implementation: `OKFDocumentRepository`
Future replacements: `DatabaseDocumentRepository`, `MilvusDocumentRepository`, etc.
Service layer must not depend on concrete repository implementation.

### Retriever Abstraction

```python
class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]: ...
```

Current: `KeywordRetriever` (simple text matching)
Future: `VectorRetriever`, `FAISSRetriever`, `HybridRetriever`

### Chunking (Runtime Only)

- Use heading-aware chunking on Markdown content
- Chunks are runtime objects, NOT persisted back to OKF files
- Chunk model: `chunk_id`, `document_id`, `title`, `heading`, `content`, `source_path`

## API Endpoints

### GET /health
```json
{"status": "ok", "service": "enterprise-kb-api", "version": "0.1.0"}
```

### GET /documents
Query params: `keyword`, `tag`, `page` (default 1), `page_size` (default 20)

Response:
```json
{
  "items": [{"document_id": "...", "title": "...", "author": "...", "created_at": "...", "tags": [...], "source_path": "..."}],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

Do NOT include full `content` in list response.

### GET /documents/{document_id}
Response includes all summary fields + `content` (Markdown body, no YAML frontmatter).

404 error format:
```json
{"error": {"code": "DOCUMENT_NOT_FOUND", "message": "Document 'xxx' was not found"}}
```

### GET /search
Query params: `q` (required), `top_k` (default 5)

Response:
```json
{
  "query": "...",
  "results": [
    {"chunk_id": "...", "document_id": "...", "title": "...", "heading": "...", "content": "...", "score": 0.92, "source_path": "..."}
  ]
}
```

## Pydantic Schemas

Define at minimum:
- `DocumentSummary`
- `DocumentDetail`
- `DocumentListResponse`
- `SearchResult`
- `SearchResponse`
- `HealthResponse`
- `ErrorResponse`

API schemas must NOT expose internal Path objects.

## Configuration

- Use environment variables for API config (not `doc_to_okf_config.yaml`)
- Key variables:
  - `KB_OKF_DIR` (default: `./generated`)
  - `KB_HOST` (default: `0.0.0.0`)
  - `KB_PORT` (default: `8000`)
- Do NOT modify `doc_to_okf_config.yaml` semantics

## Actual Directory Structure (Implemented)

```
doc_service/
├── __init__.py
├── main.py                          # FastAPI app entry point
├── api/
│   ├── __init__.py
│   ├── dependencies.py              # Service wiring (singleton factory)
│   ├── routes_health.py             # GET /health
│   └── routes_documents.py          # GET /documents, /documents/{id}, /search
├── schemas/
│   ├── __init__.py
│   ├── document.py                  # DocumentSummary, DocumentDetail, DocumentListResponse
│   ├── search.py                    # SearchResult, SearchResponse
│   └── common.py                    # HealthResponse, ErrorDetail, ErrorResponse
├── domain/
│   ├── __init__.py
│   └── document.py                  # DocumentRecord dataclass
├── services/
│   ├── __init__.py
│   └── knowledge_service.py         # KnowledgeService orchestration
├── repositories/
│   ├── __init__.py
│   ├── base.py                      # DocumentRepository Protocol
│   └── okf_document_repository.py   # OKFDocumentRepository (file-based)
├── retrieval/
│   ├── __init__.py
│   ├── retriever.py                 # Retriever Protocol + ChunkResult
│   ├── keyword_retriever.py         # KeywordRetriever (CJK-aware)
│   └── chunker.py                   # Heading-aware Markdown chunker
└── core/
    ├── __init__.py
    └── config.py                    # Settings from env vars
```

## MCP Compatibility (Design For, Don't Implement)

Future MCP tool mapping:
- `list_documents` → GET /documents
- `query_documents` → GET /search
- `get_document` → GET /documents/{document_id}

MCP will call FastAPI over HTTP — it should never directly access Repository, Retriever, or OKF files.

## Future Extension Points

### Next phase (Vector DB):
- Replace `KeywordRetriever` with `VectorRetriever` / `FAISSRetriever`
- Add `src/embedding/` module
- Add `generated/vector_store/` for FAISS index
- API contract stays the same

### Later phase (RAG):
- Add `POST /query` endpoint
- Add `src/rag/` module (pipeline, prompt, context builder)
- Add LLM Provider abstraction
- Search results already contain fields needed for RAG context

## Testing Requirements

- Use existing `generated/` OKF files or create `tests/fixtures/okf/` with sample files
- Do NOT modify the import script for testing
- Required test files:
  - `test_health.py`
  - `test_document_repository.py`
  - `test_documents_api.py`
  - `test_document_detail_api.py`
  - `test_search_api.py`
  - `test_not_found.py`

## Startup

```bash
uvicorn doc_service.main:app --reload
```

## Verification Checklist

1. `curl http://localhost:8000/health` → 200
2. `curl http://localhost:8000/documents` → list of document summaries
3. `curl http://localhost:8000/documents/<id>` → full document
4. `curl "http://localhost:8000/search?q=<keyword>&top_k=5"` → search results
5. `pytest` → all tests pass
6. `http://localhost:8000/docs` → Swagger UI accessible
