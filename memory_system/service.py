"""
memory_system.service — Main pipeline orchestration.

This module is the single entry point for the conversational memory system.
It wires together all components and implements the full request pipeline.

Pipeline (synchronous path — user waits for this):
    1.  Save current user turn to SQLite
    2.  Fetch recent N turns (RECENT_TURNS_WINDOW)
    3.  Query Rewrite: current query + recent turns → rewritten_query
    4.  Embed rewritten_query
    5.  Retriever.retrieve(rewritten_query, top_k, filters={"status": "active"})
    6.  Source Hydration: memory.source_turn_id → raw source turn from SQLite
    7.  Context Assembly: system + recent turns + retrieved historical context
    8.  LLM generate answer
    9.  Save assistant turn to SQLite
    10. Return answer to caller
    11. [Async] Memory Extraction → Dedup → SQLite write → Chroma index update

Key design invariants:
    - Memory Extraction is async and does NOT block the main response path.
    - SQLite is the source of truth; Chroma is the retrieval index.
    - Retrieved memories are hydrated from SQLite via source_turn_id before
      being assembled into context — memory.content alone is not factual source.
    - recent_turns = conversational continuity (last N turns)
    - retrieved_historical_context = semantic retrieval from earlier in conversation
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import List, Optional

from memory_system import config
from memory_system.context.assembler import SYSTEM_PROMPT, ContextAssembler
from memory_system.embedding import Embedder, get_embedder
from memory_system.llm.client import LLMClient, get_llm_client
from memory_system.memory.dedup import MemoryDeduplicator
from memory_system.memory.extractor import MemoryExtractor
from memory_system.models import Memory, MemoryStatus, RetrievedMemory
from memory_system.query.rewriter import QueryRewriter
from memory_system.retrieval.base import Retriever
from memory_system.retrieval.vector_retriever import ChromaRetriever
from memory_system.storage.sqlite_store import SQLiteStore
from memory_system.storage.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Orchestrates the full conversational memory pipeline.

    Dependency injection makes each component independently testable
    and swappable (e.g., replacing ChromaRetriever with HybridRetriever).
    """

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        vector_store: ChromaVectorStore,
        embedder: Embedder,
        llm_client: LLMClient,
        retriever: Retriever,
    ) -> None:
        self._sqlite = sqlite_store
        self._vector = vector_store
        self._embedder = embedder
        self._llm = llm_client
        self._retriever = retriever

        self._rewriter = QueryRewriter(llm_client)
        self._extractor = MemoryExtractor(llm_client)
        self._deduplicator = MemoryDeduplicator(llm_client, embedder, vector_store, sqlite_store)
        self._assembler = ContextAssembler()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(self, conversation_id: str, user_query: str) -> str:
        """
        Process a user message and return the assistant's response.

        This is a synchronous method. Memory extraction runs asynchronously
        after the response is returned.

        Args:
            conversation_id: The conversation session ID.
            user_query:      The raw user message.

        Returns:
            The assistant's response string.
        """
        logger.info(
            "MemoryService.chat: conv=%s query='%s'",
            conversation_id,
            user_query[:80],
        )

        # ----------------------------------------------------------------
        # Step 1: Save current user turn to SQLite
        # ----------------------------------------------------------------
        user_turn = self._sqlite.save_turn(
            conversation_id=conversation_id,
            role="user",
            content=user_query,
        )
        logger.debug("Saved user turn: id=%s", user_turn.id)

        # ----------------------------------------------------------------
        # Step 2: Fetch recent turns (for query rewrite context)
        # Recent turns = conversational continuity, NOT retrieved memories
        # We fetch N+1 to get context turns before the current one,
        # then exclude the just-saved user turn for the rewrite context.
        # ----------------------------------------------------------------
        all_recent = self._sqlite.get_recent_turns(
            conversation_id, config.RECENT_TURNS_WINDOW + 1
        )
        # Exclude the current user turn from the context window
        recent_context_turns = [t for t in all_recent if t.id != user_turn.id][
            -config.RECENT_TURNS_WINDOW:
        ]

        # ----------------------------------------------------------------
        # Step 3: Query Rewrite
        # Resolves references in the current query using recent turns
        # ----------------------------------------------------------------
        rewrite_result = self._rewriter.rewrite(user_query, recent_context_turns)
        rewritten_query = rewrite_result.rewritten_query

        # ----------------------------------------------------------------
        # Step 4 & 5: Embed rewritten query + Retrieve memories
        # Only ACTIVE memories are retrieved (deprecated ones are excluded)
        # ----------------------------------------------------------------
        retrieved = self._retriever.retrieve(
            query=rewritten_query,
            top_k=config.RETRIEVAL_TOP_K,
            filters={"status": MemoryStatus.ACTIVE.value},
        )

        # ----------------------------------------------------------------
        # Step 6: Source Hydration
        # Retrieved memories point to source_turn_id in SQLite.
        # The raw source turn contains the actual factual content.
        # memory.content alone is NOT a complete factual source.
        # ----------------------------------------------------------------
        hydrated = self._hydrate_memories(retrieved)

        # ----------------------------------------------------------------
        # Step 7: Context Assembly
        # recent_turns  = last N turns for conversational continuity
        # retrieved     = hydrated historical context for depth
        # ----------------------------------------------------------------
        assembled = self._assembler.assemble(
            system_prompt=SYSTEM_PROMPT,
            recent_turns=recent_context_turns,
            retrieved_memories=hydrated,
        )

        # ----------------------------------------------------------------
        # Step 8: LLM Generate Answer
        # ----------------------------------------------------------------
        messages = self._assembler.build_llm_messages(assembled, user_query)
        answer = self._generate_answer(messages, user_query)

        # ----------------------------------------------------------------
        # Step 9: Save assistant turn to SQLite
        # (must be saved BEFORE async extraction so extraction can reference it)
        # ----------------------------------------------------------------
        assistant_turn = self._sqlite.save_turn(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
        )
        logger.debug("Saved assistant turn: id=%s", assistant_turn.id)

        # ----------------------------------------------------------------
        # Step 10: Return answer to caller
        # ----------------------------------------------------------------
        logger.info(
            "MemoryService.chat: answer='%s' conv=%s",
            answer[:80],
            conversation_id,
        )

        # ----------------------------------------------------------------
        # Step 11: Async Memory Extraction
        # This fires AFTER the answer is returned. It does NOT block the caller.
        # Uses asyncio if an event loop is running; otherwise runs in a thread.
        # ----------------------------------------------------------------
        self._schedule_async_extraction(
            conversation_id=conversation_id,
            user_query=user_query,
            assistant_response=answer,
            source_turn_id=user_turn.id,
        )

        return answer

    # ------------------------------------------------------------------
    # Async Memory Extraction
    # ------------------------------------------------------------------

    def _schedule_async_extraction(
        self,
        conversation_id: str,
        user_query: str,
        assistant_response: str,
        source_turn_id: str,
    ) -> None:
        """
        Schedule memory extraction to run asynchronously.

        Strategy:
            - If an asyncio event loop is running (e.g., inside FastAPI),
              schedule as a background task via asyncio.create_task().
            - Otherwise (e.g., sync script), use asyncio.run() in a thread
              via concurrent.futures to avoid blocking.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(
                    self._async_extract_and_store(
                        conversation_id, user_query, assistant_response, source_turn_id
                    )
                )
                logger.debug("Memory extraction scheduled as async task (event loop running)")
            else:
                self._run_extraction_in_thread(
                    conversation_id, user_query, assistant_response, source_turn_id
                )
        except RuntimeError:
            self._run_extraction_in_thread(
                conversation_id, user_query, assistant_response, source_turn_id
            )

    def _run_extraction_in_thread(
        self,
        conversation_id: str,
        user_query: str,
        assistant_response: str,
        source_turn_id: str,
    ) -> None:
        """Run extraction in a background thread for synchronous callers."""
        import threading

        def _run() -> None:
            asyncio.run(
                self._async_extract_and_store(
                    conversation_id, user_query, assistant_response, source_turn_id
                )
            )

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        logger.debug("Memory extraction scheduled in background thread")

    async def _async_extract_and_store(
        self,
        conversation_id: str,
        user_query: str,
        assistant_response: str,
        source_turn_id: str,
    ) -> None:
        """
        Async memory extraction pipeline:
            Extract → Embed → Dedup → SQLite write → Chroma index update
        """
        try:
            logger.info(
                "Async extraction started: conv=%s source_turn=%s",
                conversation_id,
                source_turn_id,
            )

            # Extract
            extract_result = self._extractor.extract(user_query, assistant_response)
            if not extract_result.should_store:
                logger.info("Async extraction: should_store=False, skipping")
                return

            new_content = extract_result.content

            # Dedup check
            decision, existing_memory = self._deduplicator.check(new_content)
            logger.info("Async extraction: dedup_decision=%s", decision)

            if decision == "skip":
                # Duplicate — do not insert
                return

            if decision == "update" and existing_memory is not None:
                # Deprecate old memory in SQLite
                self._sqlite.deprecate_memory(existing_memory.id)
                # Update Chroma metadata to reflect deprecated status
                self._vector.update_metadata(
                    existing_memory.id,
                    {
                        "conversation_id": existing_memory.conversation_id,
                        "status": MemoryStatus.DEPRECATED.value,
                        "created_at": existing_memory.created_at.isoformat(),
                    },
                )
                logger.info(
                    "Async extraction: deprecated existing memory id=%s", existing_memory.id
                )

            # Insert new memory (both "insert" and "update" paths)
            new_memory = self._sqlite.save_memory(
                conversation_id=conversation_id,
                source_turn_id=source_turn_id,
                content=new_content,
            )

            # Embed and index in Chroma
            new_embedding = self._embedder.embed(new_content)
            self._vector.upsert(
                doc_id=new_memory.id,
                embedding=new_embedding,
                metadata={
                    "conversation_id": conversation_id,
                    "status": MemoryStatus.ACTIVE.value,
                    "created_at": new_memory.created_at.isoformat(),
                },
                document=new_content,
            )

            logger.info(
                "Async extraction complete: new memory id=%s content='%s'",
                new_memory.id,
                new_content[:60],
            )

        except Exception as exc:  # pylint: disable=broad-except
            # Extraction errors must never crash the main thread
            logger.exception(
                "Async extraction failed: conv=%s error=%s", conversation_id, exc
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _hydrate_memories(
        self, retrieved: List[RetrievedMemory]
    ) -> List[RetrievedMemory]:
        """
        Source Hydration: fetch the raw source turn from SQLite for each memory.

        memory.source_turn_id → SQLite turns table → raw Turn object

        The raw turn contains the original user query that generated this memory.
        This is the actual factual content — memory.content is only the theme label.
        """
        hydrated: List[RetrievedMemory] = []
        for rm in retrieved:
            source_turn = self._sqlite.get_turn_by_id(rm.memory.source_turn_id)
            if source_turn is None:
                logger.warning(
                    "Source hydration: turn not found for memory id=%s source_turn_id=%s",
                    rm.memory.id,
                    rm.memory.source_turn_id,
                )
            hydrated.append(
                RetrievedMemory(
                    memory=rm.memory,
                    similarity=rm.similarity,
                    source_turn=source_turn,
                )
            )
        return hydrated

    def _generate_answer(self, messages: List[dict], user_query: str) -> str:
        """
        Call the LLM to generate a response.

        For answer generation, we call the LLM directly (not through chat_json)
        since the answer is free text, not structured JSON.
        Falls back gracefully if the LLM client is a mock.
        """
        from memory_system.llm.client import MockLLMClient, OpenAILLMClient

        if isinstance(self._llm, MockLLMClient):
            return f"[Mock answer for query: {user_query[:60]}]"

        if isinstance(self._llm, OpenAILLMClient):
            try:
                response = self._llm._client.chat.completions.create(
                    model=self._llm._model,
                    messages=messages,
                    max_tokens=self._llm._max_tokens,
                    temperature=0,
                )
                answer = response.choices[0].message.content or ""
                logger.info(
                    "LLM answer generated: len=%d preview='%s'",
                    len(answer),
                    answer[:100],
                )
                return answer
            except Exception as exc:
                logger.exception("LLM answer generation failed: %s", exc)
                return f"[Error generating answer: {exc}]"

        # Fallback for other LLMClient implementations
        raw = self._llm.chat_json(SYSTEM_PROMPT, user_query)
        return raw.get("answer", "[No answer generated]")


# ---------------------------------------------------------------------------
# Factory — creates a fully-wired MemoryService instance
# ---------------------------------------------------------------------------

def create_service(
    sqlite_db_path: Optional[str] = None,
    chroma_persist_dir: Optional[str] = None,
    llm_client: Optional[LLMClient] = None,
    embedder: Optional[Embedder] = None,
) -> MemoryService:
    """
    Create and initialise a MemoryService with all dependencies wired.

    Args:
        sqlite_db_path:    Override SQLite path (default: from config).
        chroma_persist_dir: Override Chroma dir (default: from config).
        llm_client:        Inject custom LLMClient (default: auto from config).
        embedder:          Inject custom Embedder (default: auto from config).

    Returns:
        A fully initialised MemoryService ready to call .chat().
    """
    db_path = sqlite_db_path or config.SQLITE_DB_PATH
    chroma_dir = chroma_persist_dir or config.CHROMA_PERSIST_DIR

    sqlite_store = SQLiteStore(db_path)
    sqlite_store.init_db()

    vector_store = ChromaVectorStore(
        persist_dir=chroma_dir,
        collection_name=config.CHROMA_COLLECTION_NAME,
    )

    _embedder = embedder or get_embedder()
    _llm_client = llm_client or get_llm_client()

    retriever = ChromaRetriever(
        embedder=_embedder,
        vector_store=vector_store,
        sqlite_store=sqlite_store,
    )

    return MemoryService(
        sqlite_store=sqlite_store,
        vector_store=vector_store,
        embedder=_embedder,
        llm_client=_llm_client,
        retriever=retriever,
    )
