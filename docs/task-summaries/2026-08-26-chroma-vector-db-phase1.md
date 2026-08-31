# Task Completion Record — Chroma Vector DB (Phase 1)

- **Date:** 2026-08-26
- **Status:** COMPLETED
- **Goal:** Make the pipeline `embedding → Chroma → similarity search` visible and
  runnable. Add a `--vector-db` switch to the importer, a `vector_service/` package
  with a Chroma-backed store and a CLI (`search` + `stats`), and verify end-to-end.
- **Scope guard:** No BM25, reranker, hybrid search, MCP changes, LLM, or context
  assembly. This phase only validates Embedding → Chroma → Vector Search.

---

## 1. What was implemented

**New dependency**
- `chromadb>=1.5.0` added to `requirements.txt` (resolved version installed: `chromadb 1.5.9`).
- `vector_db/` added to `.gitignore`.

**New package `vector_service/`**
- `config.py` — constants: `DEFAULT_VECTOR_DB_DIR="vector_db"`, `COLLECTION_NAME="okf_chunks"`,
  `DISTANCE_SPACE="cosine"`, `DEFAULT_TOP_K=5`.
- `chroma_store.py` — `ChromaStore`, a thin wrapper over a Chroma persistent collection:
  - `add_embedded_chunks(chunks)` — upsert with `chunk_id` as primary key (idempotent);
    `content` → document, remaining OKF fields → metadata, precomputed vector → embedding.
  - `query(query_vector, top_k)` — Top-K nearest neighbors, returns distance + text + metadata.
  - `stats()` — collection name, record count, persist dir, distance space, embedding dim.
  - The wrapper does not embed text itself (callers pass vectors), keeping embedding and
    storage decoupled — so a future MCP tool can reuse it unchanged.
- `cli.py` — `python -m vector_service.cli`:
  - `search "<query>" [--top-k 5] [--db-dir ...]` — embeds the query with `LocalEmbedder`
    (same model as import), queries Chroma, prints rank/distance/metadata/text.
  - `stats [--db-dir ...]` — prints collection size and basic info.

**Modified `embedding_service/main_import.py`**
- Added `--vector-db` (default off) and `--vector-db-dir` flags. Default behavior is
  unchanged: JSON is still written to `embedding/` exactly as before, and `chromadb` is
  only imported when `--vector-db` is passed.
- When enabled, each document's embedded chunks are also upserted into the Chroma store,
  and a final line reports the collection record count.

**Governance**
- `.kiro/steering/agents.md` — added the rule "Always Write a Task Summary" (every completed
  task, success or failure, must produce a `docs/task-summaries/` file).

**Docs**
- `README.md` — new "Chroma / Vector DB" chapter with write + query examples, code file:line
  references, and a flow diagram matching the existing style.

## 2. How the retrieval works (brief)

1. At import time each OKF chunk is embedded (SBERT `all-MiniLM-L6-v2`, 384-dim, normalized)
   and upserted into the `okf_chunks` collection with metadata.
2. At query time the query text is embedded with the same model and sent to Chroma, which
   returns the Top-K nearest chunks by cosine distance (`distance = 1 - cosine similarity`).

## 3. Verification (commands + results)

- **Import:** `python embedding_service/main_import.py --vector-db`
  → `8 succeeded, 0 failed`; `Vector DB: collection 'okf_chunks' now holds 43 records`.
- **Stats:** `python -m vector_service.cli stats`
  → `count (records): 43`, `distance_space: cosine`, `embedding_dimension: 384`,
  `persist_dir: .../vector_db`.
- **Search:** `python -m vector_service.cli search "What mandatory fields must be included in a compliance evidence bundle?" --top-k 3`
  → Top-1 distance `0.4110`, chunk `...playbook-2028-chunk-014`, heading
  "Acceptance criteria for compliance reviewers"; Top-2/3 are chunk-002 / chunk-012 of the
  same playbook. These match the existing embedding/MCP retrieval order, and the distance
  is consistent with the earlier similarity score (0.4110 ≈ 1 − 0.589).
- **Default unchanged:** `--help` shows the new flags; without `--vector-db`, `chromadb` is
  not imported and `vector_db/` is not touched.

## 4. Known limitations & assumptions

- Chroma is loaded with the precomputed vectors from the importer; the store never embeds
  text on its own. The CLI `search` embeds the query separately via `LocalEmbedder`.
- `heading` may be empty for chunks without one (Chroma metadata cannot store `None`, so it
  is coerced to `""` on write and back to `None` on read).
- Upsert is keyed by `chunk_id`; deleting a chunk from `generated/` does not remove it from
  Chroma (no reconciliation/delete in Phase 1).
- Single collection, single embedding model. No auth, no server mode (local persistent only).

## 5. Future work (explicitly out of scope here)

- MCP tool that queries Chroma (reusing `ChromaStore` — interface already isolated).
- Swap/extend backends behind the existing `doc_service` `Retriever` protocol.
- BM25 / hybrid search / reranking / retrieval evaluation / LLM judge.

## 6. Files added / modified

**Added:** `vector_service/__init__.py`, `vector_service/config.py`,
`vector_service/chroma_store.py`, `vector_service/cli.py`,
`docs/task-summaries/2026-08-26-chroma-vector-db-phase1.md`.

**Modified:** `embedding_service/main_import.py`, `requirements.txt`, `.gitignore`,
`.kiro/steering/agents.md`, `README.md`.
