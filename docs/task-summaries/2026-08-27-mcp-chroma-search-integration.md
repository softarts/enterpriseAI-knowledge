# Task Completion Record — MCP + Chroma Search Integration

- **Date:** 2026-08-27
- **Status:** COMPLETED
- **Goal:** Wire Chroma vector DB into MCP so Kiro can call `search_chroma(query, top_k)`
  through MCP, have the query embedded via SBERT, searched against the Chroma persistent
  store, and receive ranked results — completing the chain:
  `Kiro → MCP → Embedding → Chroma DB → Search Results → MCP Response → Kiro`.
- **Scope guard:** No BM25, reranker, hybrid search, LLM API, agent, reflection, or
  context assembly. This task only adds the Chroma→MCP engineering wiring.

---

## 1. What was implemented

**New MCP tool: `search_chroma`** (`doc_service/mcp/server.py:176`)
- Accepts `query` (str) and `top_k` (int, default 5).
- Calls `get_local_embedder().embed_query(query)` to generate the query vector using the
  same SBERT model used at import time (all-MiniLM-L6-v2, 384-dim).
- Calls `get_chroma_store().query(query_vector, top_k)` to search the persistent Chroma
  collection (`okf_chunks` in `vector_db/`, cosine distance).
- Returns JSON: `{ query, top_k, backend: "chroma", results: [...] }`.
- Each result: `rank, distance, score (1-distance), document_id, heading, chunk_id, title,
  source_path, text`.

**New dependency singletons** (`doc_service/api/dependencies.py`)
- `get_chroma_store()` (line 76): lazy `ChromaStore` singleton.
- `get_local_embedder()` (line 89): lazy `LocalEmbedder` singleton.
- Both reset by `reset_service()` (used in tests).

**Tests** (`tests/test_mcp_tools.py`)
- `test_search_chroma_shape`: verifies envelope, field contract, distance/score complementarity.
- `test_search_chroma_respects_top_k`: verifies top_k limit.
- Tool-count assertion updated from 4 → 5.
- All 13 tests pass (anyio teardown errors remain cosmetic).

## 2. Complete call chain (with file:line)

```
Kiro
  → MCP tool `search_chroma(query, top_k)`       doc_service/mcp/server.py:176
    → get_local_embedder()                        doc_service/api/dependencies.py:89
      → LocalEmbedder.embed_query(query)          embedding_service/embedder.py:38
    → get_chroma_store()                          doc_service/api/dependencies.py:76
      → ChromaStore.query(query_vector, top_k)    vector_service/chroma_store.py:146
        → Chroma PersistentClient (vector_db/)
    → format results as JSON
  → MCP Response (JSON)
Kiro (receives context, synthesizes answer)
```

## 3. Test commands & results

**Unit tests:**
```
python -m pytest tests/test_mcp_tools.py -q
→ 13 passed, 1 warning, 13 errors in 113.87s
  (errors are cosmetic anyio teardown, not assertion failures)
```

**End-to-end MCP test (via MCP Client → server in-process):**
```
Query: "What mandatory fields must be included in a compliance evidence bundle?"
top_k: 3, backend: chroma

[1] distance=0.411  score=0.589  chunk-014  "Acceptance criteria for compliance reviewers"
[2] distance=0.4714 score=0.5286 chunk-002  "Key definitions"
[3] distance=0.4823 score=0.5177 chunk-012  "Risk exceptions and approval workflow"
```
Results match both the CLI (`python -m vector_service.cli search ...`) and the in-memory
embedding retrieval (`search_knowledge`), confirming Chroma search is consistent.

**Server startup:**
```
python -m doc_service.mcp_main
→ REST API: http://0.0.0.0:8000
→ MCP Server: http://0.0.0.0:8001/mcp
→ 5 tools available (list_documents, query_documents, search_knowledge, search_chroma, get_document)
```

## 4. Encountered issues

- **Kiro MCP tool binding cache:** After restarting the server with the new tool, the Kiro
  client still had the old 4-tool list cached (`mcp_enterprise_kb_search_chroma` not found).
  Workaround: reconnect the MCP server in Kiro (command palette → "MCP: Reconnect Server").
  This is a Kiro client behavior, not a server bug.
- **SBERT model cold-start:** First call to `search_chroma` is slow (~10s) because the
  SBERT model downloads weights from HuggingFace. Subsequent calls are instant (singleton
  cached). Not a blocking issue.

## 5. Files added / modified

| Action | File | Summary |
|--------|------|---------|
| Modified | `doc_service/mcp/server.py` | Added `search_chroma` tool (line 176) |
| Modified | `doc_service/api/dependencies.py` | Added `get_chroma_store()` (76) + `get_local_embedder()` (89) |
| Modified | `tests/test_mcp_tools.py` | Tool count 4→5; added 2 search_chroma tests |
| Added | `docs/task-summaries/2026-08-27-mcp-chroma-search-integration.md` | This file |
| Modified | `README.md` | New "MCP + Chroma Search" chapter |

**Existing code NOT modified:**
- `vector_service/chroma_store.py` — reused unchanged.
- `embedding_service/embedder.py` — reused unchanged.
- `vector_service/cli.py` — CLI search still works independently.
- Existing MCP tools (`search_knowledge`, `query_documents`, etc.) — unchanged.

## 6. Known limitations

- `search_chroma` requires Chroma data to exist in `vector_db/`. If empty, returns `[]`.
  The user must import first: `python embedding_service/main_import.py --vector-db`.
- Cold-start model load on first call (~10s). After that, singleton is reused.
- Kiro needs to reconnect MCP to discover newly added tools.
- No reconciliation: chunks deleted from `generated/` remain in Chroma until manually cleaned.

## 7. Future work (explicitly out of scope)

- Update `enterprise-knowledge` skill to also reference `search_chroma`.
- BM25, hybrid search, reranking.
- LLM-as-judge evaluation of Chroma-backed answers.
- ChromaRetriever implementing the `Retriever` protocol (to replace `EmbeddingRetriever`).
