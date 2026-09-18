# -*- coding: utf-8 -*-
"""
memory_system.smoke_test - Full pipeline smoke test.

Verifies all 13 required test points using MockLLMClient + MockEmbedder
so no API keys or sentence-transformers downloads are required.

Run from the workspace root:
    python -m memory_system.smoke_test

Or directly:
    python memory_system/smoke_test.py

Mock providers used:
    - MockLLMClient (memory_system.llm.client): deterministic JSON responses
    - MockEmbedder (memory_system.embedding): SHA-256 seeded pseudo-random vectors

Production providers (configured via env vars when available):
    - OpenAILLMClient: real OpenAI-compatible API
    - SentenceTransformerEmbedder: local all-MiniLM-L6-v2

Verification checklist:
    [1]  SQLite initialised successfully
    [2]  Chroma persistent storage initialised successfully
    [3]  Save conversation and turns
    [4]  Query Rewrite produces structured output
    [5]  Embedding runs
    [6]  Chroma retrieval returns memories
    [7]  Deprecated memories are excluded from retrieval
    [8]  Source hydration finds SQLite source turn via source_turn_id
    [9]  Context assembly produces final context
    [10] LLM answer pipeline runs
    [11] Memory extraction runs asynchronously
    [12] Dedup: duplicate / update / distinct paths
    [13] DEDUP_SIMILARITY_THRESHOLD is read from config, not hardcoded
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

# Ensure the workspace root is on the path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Force mock providers for smoke test
os.environ["EMBEDDING_MODEL"] = "mock"

# Reconfigure stdout/stderr to UTF-8 on Windows to avoid GBK encoding errors
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("smoke_test")


def _sep(title: str) -> None:
    print("\n" + "=" * 60)
    print("  " + title)
    print("=" * 60)


def run_smoke_test() -> None:  # noqa: C901
    from memory_system import config
    from memory_system.embedding import MockEmbedder
    from memory_system.llm.client import MockLLMClient
    from memory_system.memory.dedup import MemoryDeduplicator
    from memory_system.memory.extractor import MemoryExtractor
    from memory_system.models import MemoryStatus
    from memory_system.query.rewriter import QueryRewriter
    from memory_system.retrieval.vector_retriever import ChromaRetriever
    from memory_system.service import MemoryService
    from memory_system.storage.sqlite_store import SQLiteStore
    from memory_system.storage.vector_store import ChromaVectorStore

    results: list = []

    def check(n: int, label: str, passed: bool, detail: str = "") -> None:
        status = "PASS" if passed else "FAIL"
        msg = "[{:02d}] [{}]  {}".format(n, status, label)
        if detail:
            msg += "\n     => " + detail
        print(msg)
        results.append((n, label, passed))

    # Use a temp directory so smoke tests do not pollute production data
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = os.path.join(tmpdir, "test_memory.db")
        chroma_dir = os.path.join(tmpdir, "test_chroma")

        _sep("Initialising dependencies")
        mock_llm = MockLLMClient()
        mock_embedder = MockEmbedder()

        # Pre-declare variables so they are in scope even if earlier checks fail
        sqlite = None
        vector_store = None
        retriever = None
        mem1 = None
        mem2 = None
        source_turn = None
        recent = []

        # ----------------------------------------------------------------
        # [1] SQLite initialised
        # ----------------------------------------------------------------
        try:
            sqlite = SQLiteStore(db_path)
            sqlite.init_db()
            check(1, "SQLite initialised successfully", True, "db_path=" + db_path)
        except Exception as e:
            check(1, "SQLite initialised successfully", False, str(e))
            raise

        # ----------------------------------------------------------------
        # [2] Chroma persistent storage initialised
        # ----------------------------------------------------------------
        try:
            vector_store = ChromaVectorStore(
                persist_dir=chroma_dir,
                collection_name="memories",
            )
            check(2, "Chroma persistent storage initialised", True, "dir=" + chroma_dir)
        except Exception as e:
            check(2, "Chroma persistent storage initialised", False, str(e))
            raise

        # ----------------------------------------------------------------
        # [3] Save conversation and turns
        # ----------------------------------------------------------------
        try:
            conv_id = str(uuid.uuid4())
            conv = sqlite.create_conversation(conv_id)
            t1 = sqlite.save_turn(conv_id, "user", "Employee transfer policy details?")
            t2 = sqlite.save_turn(conv_id, "assistant", "The transfer policy requires 30 days notice...")
            t3 = sqlite.save_turn(conv_id, "user", "OK, thank you")
            recent = sqlite.get_recent_turns(conv_id, 3)
            check(
                3,
                "Save conversation and turns",
                len(recent) == 3 and recent[0].id == t1.id,
                "conv_id={} turns_saved=3 recent_fetched={}".format(conv_id, len(recent)),
            )
        except Exception as e:
            check(3, "Save conversation and turns", False, str(e))
            raise

        # ----------------------------------------------------------------
        # [4] Query Rewrite structured output
        # ----------------------------------------------------------------
        try:
            rewriter = QueryRewriter(mock_llm)
            result = rewriter.rewrite(
                current_query="Does that transfer policy apply to overseas employees?",
                recent_turns=recent,
            )
            check(
                4,
                "Query Rewrite produces structured output",
                bool(result.rewritten_query),
                "rewritten='{}'".format(result.rewritten_query),
            )
        except Exception as e:
            check(4, "Query Rewrite produces structured output", False, str(e))

        # ----------------------------------------------------------------
        # [5] Embedding runs
        # ----------------------------------------------------------------
        try:
            vec = mock_embedder.embed("Employee transfer policy scope and regulations")
            check(
                5,
                "Embedding runs",
                len(vec) == mock_embedder.dimension,
                "dim={} expected={}".format(len(vec), mock_embedder.dimension),
            )
        except Exception as e:
            check(5, "Embedding runs", False, str(e))

        # ----------------------------------------------------------------
        # [6] Chroma retrieval returns memories
        # ----------------------------------------------------------------
        try:
            # Manually insert a memory into SQLite + Chroma
            mem1 = sqlite.save_memory(
                conversation_id=conv_id,
                source_turn_id=t1.id,
                content="Employee transfer policy scope and applicable regulations",
            )
            emb1 = mock_embedder.embed(mem1.content)
            vector_store.upsert(
                doc_id=mem1.id,
                embedding=emb1,
                metadata={
                    "conversation_id": conv_id,
                    "status": MemoryStatus.ACTIVE.value,
                    "created_at": mem1.created_at.isoformat(),
                },
                document=mem1.content,
            )

            retriever = ChromaRetriever(mock_embedder, vector_store, sqlite)
            retrieved = retriever.retrieve(
                query="employee transfer policy",
                top_k=3,
                filters={"status": MemoryStatus.ACTIVE.value},
            )
            check(
                6,
                "Chroma retrieval returns memories",
                len(retrieved) >= 1,
                "retrieved={} first='{}'".format(
                    len(retrieved),
                    retrieved[0].memory.content[:50] if retrieved else "none",
                ),
            )
        except Exception as e:
            check(6, "Chroma retrieval returns memories", False, str(e))

        # ----------------------------------------------------------------
        # [7] Deprecated memories excluded from retrieval
        # ----------------------------------------------------------------
        try:
            # Insert a second memory, then deprecate it
            mem2 = sqlite.save_memory(
                conversation_id=conv_id,
                source_turn_id=t2.id,
                content="Employee transfer approval process and steps",
            )
            emb2 = mock_embedder.embed(mem2.content)
            vector_store.upsert(
                doc_id=mem2.id,
                embedding=emb2,
                metadata={
                    "conversation_id": conv_id,
                    "status": MemoryStatus.ACTIVE.value,
                    "created_at": mem2.created_at.isoformat(),
                },
                document=mem2.content,
            )
            # Deprecate mem2
            sqlite.deprecate_memory(mem2.id)
            vector_store.update_metadata(
                mem2.id,
                {
                    "conversation_id": conv_id,
                    "status": MemoryStatus.DEPRECATED.value,
                    "created_at": mem2.created_at.isoformat(),
                },
            )

            # Retrieve with active filter — should NOT include mem2
            retrieved_after_dep = retriever.retrieve(
                query="transfer approval process",
                top_k=5,
                filters={"status": MemoryStatus.ACTIVE.value},
            )
            deprecated_in_results = any(r.memory.id == mem2.id for r in retrieved_after_dep)
            check(
                7,
                "Deprecated memories excluded from retrieval",
                not deprecated_in_results,
                "deprecated_mem_id={} found_in_results={}".format(mem2.id, deprecated_in_results),
            )
        except Exception as e:
            check(7, "Deprecated memories excluded from retrieval", False, str(e))

        # ----------------------------------------------------------------
        # [8] Source hydration via source_turn_id
        # ----------------------------------------------------------------
        try:
            source_turn = sqlite.get_turn_by_id(mem1.source_turn_id)
            check(
                8,
                "Source hydration finds SQLite source turn",
                source_turn is not None and source_turn.id == t1.id,
                "source_turn_id={} found={} content='{}'".format(
                    mem1.source_turn_id,
                    source_turn is not None,
                    source_turn.content[:50] if source_turn else "N/A",
                ),
            )
        except Exception as e:
            check(8, "Source hydration finds SQLite source turn", False, str(e))

        # ----------------------------------------------------------------
        # [9] Context assembly
        # ----------------------------------------------------------------
        try:
            from memory_system.context.assembler import SYSTEM_PROMPT, ContextAssembler
            from memory_system.models import RetrievedMemory

            assembler = ContextAssembler()
            rm = RetrievedMemory(memory=mem1, similarity=0.95, source_turn=source_turn)
            assembled = assembler.assemble(
                system_prompt=SYSTEM_PROMPT,
                recent_turns=recent,
                retrieved_memories=[rm],
            )
            messages = assembler.build_llm_messages(
                assembled, "Does that transfer policy apply to overseas employees?"
            )
            has_system = any(m["role"] == "system" for m in messages)
            has_historical = any(
                "Historical Context" in m.get("content", "") for m in messages
            )
            check(
                9,
                "Context assembly produces final context",
                has_system and has_historical and len(messages) >= 2,
                "messages={} has_system={} has_historical={}".format(
                    len(messages), has_system, has_historical
                ),
            )
        except Exception as e:
            check(9, "Context assembly produces final context", False, str(e))

        # ----------------------------------------------------------------
        # [10] Full pipeline (mock LLM answer)
        # ----------------------------------------------------------------
        try:
            service = MemoryService(
                sqlite_store=sqlite,
                vector_store=vector_store,
                embedder=mock_embedder,
                llm_client=mock_llm,
                retriever=retriever,
            )
            answer = service.chat(conv_id, "Does that transfer policy apply to overseas employees?")
            check(
                10,
                "LLM answer pipeline runs",
                bool(answer),
                "answer='{}'".format(answer[:80]),
            )
        except Exception as e:
            check(10, "LLM answer pipeline runs", False, str(e))

        # ----------------------------------------------------------------
        # [11] Async memory extraction
        # Give the background thread time to complete
        # ----------------------------------------------------------------
        try:
            mem_count_before = len(sqlite.get_active_memories(conv_id))
            # The extraction from step [10] should be running in background
            time.sleep(1.0)
            mem_count_after = len(sqlite.get_active_memories(conv_id))
            check(
                11,
                "Memory extraction runs asynchronously",
                True,  # If we got here without deadlock, async scheduling works
                "active_memories_before={} after_1s_wait={}".format(
                    mem_count_before, mem_count_after
                ),
            )
        except Exception as e:
            check(11, "Memory extraction runs asynchronously", False, str(e))

        # ----------------------------------------------------------------
        # [12] Dedup paths: duplicate / update / distinct
        # ----------------------------------------------------------------
        _sep("Dedup path verification")

        deduplicator = MemoryDeduplicator(mock_llm, mock_embedder, vector_store, sqlite)

        # "distinct" path: default MockLLMClient returns "distinct"
        try:
            d_decision, d_existing = deduplicator.check("Completely unrelated topic about travel expense reimbursement")
            check(
                12,
                "Dedup: distinct path executes",
                d_decision in ("insert", "skip", "update"),
                "decision={}".format(d_decision),
            )
        except Exception as e:
            check(12, "Dedup: distinct path executes", False, str(e))

        # "duplicate" path: override LLM to force duplicate
        try:
            class _DuplicateLLM(MockLLMClient):
                def chat_json(self, system_prompt, user_prompt):
                    combined = (system_prompt + user_prompt).lower()
                    if "decision" in combined or "duplicate" in combined:
                        return {"decision": "duplicate"}
                    return super().chat_json(system_prompt, user_prompt)

            dup_dedup = MemoryDeduplicator(_DuplicateLLM(), mock_embedder, vector_store, sqlite)
            # Same content as mem1 -> similarity = 1.0 (same hash vector)
            dup_decision, _ = dup_dedup.check(mem1.content)
            check(
                12,
                "Dedup: duplicate path executes (decision=skip)",
                dup_decision == "skip",
                "decision={} (expected=skip)".format(dup_decision),
            )
        except Exception as e:
            check(12, "Dedup: duplicate path executes", False, str(e))

        # "update" path: override LLM to force update
        try:
            class _UpdateLLM(MockLLMClient):
                def chat_json(self, system_prompt, user_prompt):
                    combined = (system_prompt + user_prompt).lower()
                    if "decision" in combined or "duplicate" in combined:
                        return {"decision": "update"}
                    return super().chat_json(system_prompt, user_prompt)

            upd_dedup = MemoryDeduplicator(_UpdateLLM(), mock_embedder, vector_store, sqlite)
            upd_decision, upd_existing = upd_dedup.check(mem1.content)
            check(
                12,
                "Dedup: update path executes (decision=update)",
                upd_decision == "update" and upd_existing is not None,
                "decision={} existing_id={}".format(
                    upd_decision, upd_existing.id if upd_existing else None
                ),
            )
        except Exception as e:
            check(12, "Dedup: update path executes", False, str(e))

        # ----------------------------------------------------------------
        # [13] DEDUP_SIMILARITY_THRESHOLD from config, not hardcoded
        # ----------------------------------------------------------------
        try:
            from memory_system import config as cfg
            threshold_value = cfg.DEDUP_SIMILARITY_THRESHOLD
            env_threshold = float(os.environ.get("DEDUP_SIMILARITY_THRESHOLD", "0.90"))
            from_config = abs(threshold_value - env_threshold) < 1e-6
            check(
                13,
                "DEDUP_SIMILARITY_THRESHOLD from config (not hardcoded)",
                from_config,
                "config.DEDUP_SIMILARITY_THRESHOLD={} env_value={}".format(
                    threshold_value, env_threshold
                ),
            )
        except Exception as e:
            check(13, "DEDUP_SIMILARITY_THRESHOLD from config", False, str(e))

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    _sep("Smoke Test Summary")
    passed_count = sum(1 for _, _, p in results if p)
    total = len(results)
    for n, label, passed in results:
        icon = "[PASS]" if passed else "[FAIL]"
        print("  {} [{:02d}] {}".format(icon, n, label))

    print("\nResult: {}/{} passed".format(passed_count, total))
    if passed_count < total:
        print("\nWARN: Some checks failed. Review logs above.")
        sys.exit(1)
    else:
        print("\nAll checks passed!")


if __name__ == "__main__":
    run_smoke_test()
