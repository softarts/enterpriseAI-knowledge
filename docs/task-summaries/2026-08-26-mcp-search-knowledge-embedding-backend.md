# Task Completion Record — MCP `search_knowledge` over Embedding Retrieval

- **Date:** 2026-08-26
- **Status:** COMPLETED
- **Goal:** Close the minimal loop `Kiro → MCP → existing Retrieval → Context → Kiro` by
  adding an MCP tool `search_knowledge(query, top_k=5)` that retrieves from the project's
  **embedding (SBERT vector)** capability and returns Top-K context only. Kiro (the LLM)
  synthesizes the final answer itself.
- **Explicit non-goal:** No Chroma / vector DB was implemented in this task.

---

## 1. Current Retrieval backend

The project has two retrieval capabilities:

| Backend | Module | Data source | Method |
|---|---|---|---|
| Keyword (existing) | `doc_service/retrieval/keyword_retriever.py` | OKF `.yaml` under `generated/` (re-chunked on the fly) | term-frequency keyword matching |
| Embedding (used by this task) | `embedding_service/` (`LocalEmbedder`, `search_by_similarity`, `load_all_embeddings`) | persisted SBERT vectors under `embedding/*.json` (43 chunks) | cosine similarity (SBERT `all-MiniLM-L6-v2`, 384-dim) |

Both are exposed through the **single** `Retriever` protocol
(`doc_service/retrieval/retriever.py`):

```
retrieve(query: str, top_k: int = 5) -> List[ChunkResult]
```

`search_knowledge` is backed by the **embedding** retriever. The existing REST `/search`
and MCP `query_documents` remain on the **keyword** retriever (unchanged).

New adapter added: `doc_service/retrieval/embedding_retriever.py` (`EmbeddingRetriever`).
It reuses `embedding_service` directly — no embedding, similarity, or storage logic is
duplicated. It maps each `SimilarityResult` into the shared `ChunkResult` (a 1:1 field
mapping: `chunk_id, document_id, title, heading, content, score, source_path`).

## 2. How MCP calls it

```
Kiro
  → MCP tool  search_knowledge(query, top_k)
    → get_embedding_knowledge_service()        (doc_service/api/dependencies.py)
      → KnowledgeService.search(query, top_k)
        → Retriever protocol
          → EmbeddingRetriever.retrieve(...)   (current backend)
            → LocalEmbedder.embed_query + search_by_similarity over embedding/*.json
```

- MCP layer does not read files, embed, or score directly — it only formats the result.
- MCP returns **context only**; it never generates the final answer.
- A separate, cached embedding-backed `KnowledgeService` singleton is used so the keyword
  tools are not affected (Option A: one protocol, multiple backends).

## 3. What Context is returned

`search_knowledge` returns JSON:

```json
{
  "query": "...",
  "top_k": 5,
  "results": [
    {
      "rank": 1,
      "score": 0.589,
      "document_id": "...",
      "heading": "...",
      "chunk_id": "...",
      "title": "...",
      "source_path": "...",
      "text": "..."
    }
  ]
}
```

Results are ordered by descending cosine similarity; `rank` is 1-indexed.

## 4. Can Kiro answer based on the Context?

Yes. Verified end-to-end: querying *"What mandatory fields must be included in a compliance
evidence bundle?"* returned 3 ranked chunks led by the
`authn-audit-evidence-correlation-playbook` document (score ~0.59, heading "Acceptance
criteria for compliance reviewers"), which contains the relevant material. Kiro receives
these chunks and synthesizes the grounded answer + citations itself.

## 5. Chroma status

**Not implemented.** No Chroma, no vector DB, no migration. The current embedding backend is
the persisted JSON produced by `embedding_service/main_import.py`.

## 6. Extension points reserved for the future

- The `Retriever` protocol is the single seam. A future `ChromaRetriever` (or any vector DB)
  implements the same `retrieve(query, top_k) -> List[ChunkResult]` and is swapped in at
  `get_embedding_knowledge_service()` in `doc_service/api/dependencies.py`.
- The MCP tool signature `search_knowledge(query, top_k)` and its return shape **do not change**
  when the backend changes.
- Out of scope for this task (future work): Chroma / other vector store, a richer retrieval
  abstraction, BM25, hybrid search, reranking, retrieval evaluation, LLM-as-judge.

## 7. Files added / modified

**Added**
- `doc_service/retrieval/embedding_retriever.py` — `EmbeddingRetriever` (embedding backend behind the `Retriever` protocol).
- `docs/task-summaries/2026-08-26-mcp-search-knowledge-embedding-backend.md` — this record.

**Modified**
- `doc_service/mcp/server.py` — added the `search_knowledge` tool (existing 3 tools untouched).
- `doc_service/api/dependencies.py` — added `get_embedding_knowledge_service()` + shared repository; keyword service unchanged.
- `tests/test_mcp_tools.py` — added `search_knowledge` tests; updated tool-count assertion to 4 tools.

**Deliberately NOT modified:** `keyword_retriever.py`, `knowledge_service.py`, `embedding_service/*`, REST API routes, Kiro MCP connection (`.kiro/settings/mcp.json` still points at `http://localhost:8001/mcp`).

## 8. How to run

1. Ensure embeddings exist (already present: 43 chunks in `embedding/`). To regenerate:
   `python embedding_service/main_import.py`
2. Start the service (REST :8000 + MCP :8001): `python -m doc_service.mcp_main`
3. In Kiro, the `enterprise-kb` MCP server exposes `search_knowledge`. Call it, e.g.
   `search_knowledge("What mandatory fields must be included in a compliance evidence bundle?")`,
   then let Kiro answer from the returned context.

## 9. Verification

- `python -m pytest tests/test_mcp_tools.py` → **11 passed** (the 11 anyio teardown "errors"
  are the pre-existing, documented cosmetic client-teardown issue, not assertion failures).
- Direct call of `search_knowledge(...)` returns Top-K embedding-ranked context with the
  required fields.

## 10. Assumptions & limitations

- `EmbeddingRetriever` reads the `embedding/` directory (relative to CWD; default from
  `embedding_service.config.DEFAULT_EMBEDDING_DIR`). If empty, `search_knowledge` returns an
  empty result list and logs a hint to run the embedding import.
- Semantic quality is bounded by the existing SBERT baseline; this task does not tune retrieval.
- The embedding-backed and keyword-backed services share one repository but are separate
  `KnowledgeService` singletons, so `search_knowledge` and `query_documents` can diverge in
  results by design (different backends).

---

## Addendum (2026-08-26) — MCP-only usage + startup robustness

**Context:** In a follow-up, an "use enterprise-kb mcp" request was answered by
falling back to a direct in-process `search_knowledge` call after a raw HTTP `/mcp`
attempt failed. Root cause was a usage mistake, not a server bug: the `enterprise-kb`
MCP tools were available as tool bindings and should have been used directly. A
duplicate `python -m doc_service.mcp_main` also crashed noisily because the real
server already held ports 8000/8001.

**Fixes applied:**
1. `doc_service/mcp_main.py` — added a port preflight (`_preflight_ports`) that fails
   fast with a clear, actionable message ("port already in use / instance may already
   be running") and exit code 1, instead of a long uvicorn/asyncio traceback.
2. `.kiro/skills/enterprise-knowledge.md` — new manual skill. When the user says
   "use enterprise-knowledge mcp", enterprise knowledge MUST be retrieved via the
   `enterprise-kb` MCP tools (`search_knowledge`, `query_documents`, `list_documents`,
   `get_document`). Direct in-process calls, REST calls, raw `/mcp` HTTP, and reading
   `embedding/` or `generated/` directly are explicitly disallowed.

**Verification:**
- `search_knowledge` confirmed callable through the MCP tool binding (returned 3
  ranked chunks for the compliance-evidence query).
- Duplicate startup now prints the preflight error and exits 1 (no traceback).
