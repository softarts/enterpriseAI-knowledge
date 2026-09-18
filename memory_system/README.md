# Conversational Memory System MVP

A runnable, modular Conversational Memory System built for enterprise conversational AI workflows. It enables LLMs to answer follow-up queries that reference information discussed 5+ turns earlier by indexing, retrieving, and deduplicating conversational memories.

---

## 1. Core Scenario

A user asks a question early in a conversation (Turn 1), converses on unrelated topics for multiple turns (Turns 2–10), and then poses an elliptical follow-up question (Turn 11):

```
Turn 1:
User: "员工调动政策是什么？"
Assistant: "员工调动政策包含申请流程、审批人、适用范围..."

Turns 2–10:
[Unrelated topics: expense reports, office hours, vacation requests...]

Turn 11:
User: "那调动政策对海外员工适用吗？"
```

The system:
1. **Rewrites the query** into a standalone search query if ambiguous.
2. **Performs semantic retrieval** from vector memory storage (filtering active memories).
3. **Hydrates source turns** from relational storage to capture the exact context when the memory was created.
4. **Assembles structured prompt context** combining system instructions, historical memories + source turns, and recent window turns.
5. **Generates the follow-up answer** with plain OpenAI / mock LLM client.
6. **Extracts memories asynchronously in the background** without blocking user response latency.
7. **Performs two-stage deduplication** (vector cosine similarity check + LLM semantic resolution: `insert`, `skip`, or `update`).
8. **Supports soft-delete deprecation and updates** across SQLite and vector databases.

---

## 2. Architecture & Data Flow

```
User Query (Turn N)
         │
         ▼
┌────────────────────────────────────────────────────────┐
│ 1. MemoryService.chat()                                │
│    ├── Save user turn to SQLite (Turn N)               │
│    ├── Fetch recent window turns (e.g., last 3)        │
│    ├── QueryRewriter: resolve coreferences             │
│    ├── VectorRetriever: retrieve top-k active memories │
│    ├── Source Hydration: fetch raw turn from SQLite    │
│    ├── ContextAssembler: construct LLM message list    │
│    └── LLMClient: generate assistant response         │
└────────────────────────────────────────────────────────┘
         │
         ├─── Return response to user (low latency)
         │
         ▼ (Async Background ThreadPoolExecutor)
┌────────────────────────────────────────────────────────┐
│ 2. Background Memory Extraction & Dedup                │
│    ├── Save assistant turn to SQLite                   │
│    ├── MemoryExtractor: extract salient facts          │
│    └── MemoryDeduplicator:                             │
│        ├── Cosine similarity against active memories   │
│        ├── If sim >= threshold (0.90):                 │
│        │     LLM dedup judgment: duplicate/update/new  │
│        │     ├── duplicate -> skip                     │
│        │     ├── update    -> update SQLite + Chroma   │
│        │     └── new       -> insert new memory        │
│        └── If sim < threshold:                         │
│              Insert new memory into SQLite + Chroma    │
└────────────────────────────────────────────────────────┘
```

---

## 3. Directory Structure

```
memory_system/
├── __init__.py
├── config.py                 # Pydantic/dataclass-style config via env vars
├── models.py                 # Domain models (Turn, Conversation, MemoryItem, etc.)
├── embedding.py              # MockEmbedder, OpenAIEmbedder, SentenceTransformersEmbedder
├── service.py                # Main facade: MemoryService orchestrates end-to-end chat
├── smoke_test.py             # Self-contained 15-point smoke test
│
├── storage/
│   ├── __init__.py
│   ├── sqlite_store.py       # Conversations, turns, memory records (with JSON tags)
│   └── vector_store.py       # Chroma persistent vector store with status metadata
│
├── retrieval/
│   ├── __init__.py
│   ├── base.py               # Abstract BaseRetriever
│   └── vector_retriever.py   # Semantic search with metadata filtering & source hydration
│
├── memory/
│   ├── __init__.py
│   ├── extractor.py          # LLM-based memory fact extraction
│   └── dedup.py              # 2-stage deduplication & status update / deprecation
│
├── query/
│   ├── __init__.py
│   └── rewriter.py           # Coreference resolution query rewriter
│
├── context/
│   ├── __init__.py
│   └── assembler.py          # Formats system prompt, historical memories, and recent turns
│
├── llm/
│   ├── __init__.py
│   └── client.py             # Plain OpenAI client wrapper + MockLLMClient for testing
│
└── prompts/
    ├── extract.txt           # Memory extraction prompt template
    ├── dedup.txt             # Memory deduplication decision prompt template
    └── rewrite.txt           # Query rewriting prompt template
```

---

## 4. Key Design Decisions

1. **Dual Storage Strategy**:
   - **SQLite**: Source of truth for relational integrity (`conversations`, `turns`, `memories`). Tracks `source_turn_id`, `status` (`active` vs `deprecated`), timestamps, and tags.
   - **Chroma**: Vector indexing for semantic similarity search. Chroma stores `memory_id` in metadata and mirrors `status` for fast pre-filtering.
2. **No Framework Lock-in**:
   - No LangChain or LlamaIndex dependencies. Uses plain `openai` SDK, standard library `sqlite3`, and `chromadb`.
3. **Python 3.9 Compliance**:
   - Uses standard `typing` (`Optional`, `Union`, `List`, `Dict`) instead of PEP 604 pipe unions (`|`).
   - Clean syntax without Python 3.10+ match statements or runtime-only features.
4. **Configurable & Production-Ready**:
   - `DEDUP_SIMILARITY_THRESHOLD` (default `0.90`), `TOP_K` (default `3`), and `RECENT_TURNS_WINDOW` (default `3`) are configurable via environment variables.
   - ThreadPoolExecutor manages asynchronous extraction gracefully with thread shutdown handling.

---

## 5. Running the Smoke Test

The smoke test is completely self-contained. It uses `MockEmbedder` (SHA-256 deterministic pseudo-embedding) and `MockLLMClient`, running cleanly without any network access or API keys.

```bash
# Run from workspace root:
python -m memory_system.smoke_test
```

### Verification Points Checked (15/15 Passed):
- `[01]` SQLite database initialization and schema creation
- `[02]` Chroma persistent storage initialization
- `[03]` Conversation and multi-turn persistence and recent turn retrieval
- `[04]` Query rewriter coreference resolution
- `[05]` Embedding vector calculation (384-dim normalized floats)
- `[06]` Chroma semantic retrieval matching query to historical memory
- `[07]` Deprecated memories properly filtered out from search results
- `[08]` Source hydration linking retrieved memory back to original SQLite turn
- `[09]` Context assembler combining system prompt, memories, and recent turns
- `[10]` Full end-to-end follow-up answering pipeline
- `[11]` Asynchronous memory extraction in background thread
- `[12]` Deduplication path: distinct insertion
- `[12]` Deduplication path: duplicate skip
- `[12]` Deduplication path: content update in SQLite & Chroma
- `[13]` Dedup threshold loaded from configuration (not hardcoded)
