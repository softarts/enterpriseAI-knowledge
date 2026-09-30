"""Long-term memory (V2): store factory, retrieval, writes, extraction, tool.

All long-term memory logic lives in this module. Short-term memory
(Checkpointer + thread history) stays in app/graph.py and app/runtime.py;
app/graph.py only imports the building blocks defined here.
"""

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple
from uuid import uuid4

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import InjectedStore
from langgraph.store.base import BaseStore, IndexConfig
from langgraph.store.memory import InMemoryStore
from typing_extensions import Annotated

from . import config as app_config
from .long_memory_prompts import MEMORY_EXTRACTION_PROMPT, MemoryExtraction

logger = logging.getLogger(__name__)

EMBEDDING_DIMS: int = app_config.MEMORY_EMBEDDING_DIMS

# Index fields embedded for semantic search inside the store.
MEMORY_INDEX_FIELDS: List[str] = ["content"]


def get_user_memory_namespace(user_id: str) -> Tuple[str, str, str]:
    """Per-user namespace; no cross-user scan is possible by construction."""
    return ("users", user_id, "memories")


def create_memory_store(
    embeddings: Optional[Embeddings] = None,
    dims: int = EMBEDDING_DIMS,
) -> InMemoryStore:
    """Create the long-term memory store with a semantic IndexConfig.

    The default is an in-process InMemoryStore. The ``embeddings`` and
    ``dims`` parameters keep the seam open for swapping in a PostgresStore
    later: callers inject whatever embeddings the future store should index
    with, and only this factory needs to change its return statement.
    """
    active_embeddings = embeddings if embeddings is not None else app_config.get_embeddings()
    index = IndexConfig(
        dims=dims,
        embed=active_embeddings,
        fields=list(MEMORY_INDEX_FIELDS),
    )
    store = InMemoryStore(index=index)
    logger.info(
        "memory.longterm.store.create store=%s embeddings=%s dims=%d index_fields=%s",
        type(store).__name__,
        type(active_embeddings).__name__,
        dims,
        MEMORY_INDEX_FIELDS,
    )
    return store


def retrieve_user_memories(
    store: BaseStore,
    user_id: str,
    query: str,
    top_k: int = 3,
    raise_on_error: bool = False,
) -> List[str]:
    """Search one user's namespace; optionally propagate Store errors to tools."""
    namespace = get_user_memory_namespace(user_id)
    try:
        items = store.search(namespace, query=query, limit=top_k)
    except Exception:
        logger.warning(
            "memory.longterm.retrieve.failed user_id=%s top_k=%d",
            user_id,
            top_k,
            exc_info=True,
        )
        if raise_on_error:
            raise
        return []
    contents = [
        str(item.value["content"])
        for item in items
        if isinstance(item.value, dict) and item.value.get("content")
    ]
    logger.info(
        "memory.longterm.retrieve user_id=%s top_k=%d hits=%d",
        user_id,
        top_k,
        len(contents),
    )
    return contents


def save_user_memory(
    store: BaseStore,
    user_id: str,
    memory_content: str,
    thread_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> bool:
    """Persist one memory item under the user's namespace."""
    namespace = get_user_memory_namespace(user_id)
    payload = {
        "content": memory_content,
        "source_thread_id": thread_id,
        "source_message_id": message_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    key = f"mem_{uuid4().hex[:12]}"
    try:
        store.put(namespace=namespace, key=key, value=payload, index=["content"])
    except Exception:
        logger.warning(
            "memory.longterm.save.failed user_id=%s key=%s",
            user_id,
            key,
            exc_info=True,
        )
        return False
    logger.info(
        "memory.longterm.save user_id=%s key=%s thread_id=%s",
        user_id,
        key,
        thread_id,
    )
    return True


def extract_and_save_memory(
    store: BaseStore,
    user_id: str,
    extraction_llm: Runnable,
    extraction_input: str,
    thread_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> bool:
    """Run structured extraction and save only on an explicit store decision.

    ``extraction_llm`` must already be bound with
    ``llm.with_structured_output(MemoryExtraction)``; this function never
    parses free-form text.
    """
    try:
        extraction = extraction_llm.invoke(
            [
                SystemMessage(content=MEMORY_EXTRACTION_PROMPT),
                HumanMessage(content=extraction_input),
            ]
        )
    except Exception:
        logger.warning(
            "memory.longterm.extract.failed user_id=%s thread_id=%s",
            user_id,
            thread_id,
            exc_info=True,
        )
        return False
    should_store = bool(getattr(extraction, "should_store", False))
    memory_text = (getattr(extraction, "memory", None) or "").strip()
    logger.info(
        "memory.longterm.extract user_id=%s thread_id=%s should_store=%s",
        user_id,
        thread_id,
        should_store,
    )
    if not (should_store and memory_text):
        return False
    return save_user_memory(
        store=store,
        user_id=user_id,
        memory_content=memory_text,
        thread_id=thread_id,
        message_id=message_id,
    )


def create_search_memory_tool(default_top_k: int = 3) -> BaseTool:
    """Create the agent-facing long-term memory search tool.

    Only ``query`` is exposed to the LLM. ``config`` and ``store`` are
    injected by LangGraph at runtime and never appear in the tool schema.
    """

    @tool
    def search_memory(
        query: str,
        config: RunnableConfig,
        store: Annotated[BaseStore, InjectedStore()],
    ) -> str:
        """Search the current user's long-term memory.
        
        Call this only when the answer depends on the user's stable
        preferences, long-term background, long-term goals, or facts the user
        previously asked to remember. Do not call it for questions that can
        be answered from the current conversation alone.

        ``query`` must be a standalone, semantically complete search phrase
        that makes sense without the surrounding conversation.
        """
        try:
            logger.info("Search the current user's long-term memory.")
            configurable: Any = (config or {}).get("configurable", {})
            user_id = configurable.get("user_id")
            top_k = int(configurable.get("top_k") or default_top_k)
            if not user_id:
                logger.warning("memory.longterm.tool.missing_user_id")
                return (
                    "Tool failed: long-term memory is unavailable because "
                    "user_id is missing. Try a different approach."
                )
            memories = retrieve_user_memories(
                store=store,
                user_id=user_id,
                query=query,
                top_k=top_k,
                raise_on_error=True,
            )
            if not memories:
                logger.info(
                    "memory.longterm.tool.no_memories_found user_id=%s query=%s",
                    user_id,
                    query,
                )
                return "没有找到与查询相关的长期记忆。"
            return "找到以下相关长期记忆：\n" + "\n".join(
                f"- {item}" for item in memories
            )
        except Exception as exc:  # noqa: BLE001 - tool errors become observations
            logger.exception("memory.longterm.tool.failed")
            reason = f"memory search error ({type(exc).__name__})"
            return f"Tool failed: {reason}. Try a different approach."

    return search_memory
