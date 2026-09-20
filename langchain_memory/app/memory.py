"""Long-term memory management using LangGraph Store."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from langchain_core.embeddings import Embeddings
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.store.base import BaseStore, IndexConfig
from langgraph.store.memory import InMemoryStore

try:
    from .config import EMBEDDING_DIMS, get_embeddings
    from .prompts import MEMORY_EXTRACTION_PROMPT, MemoryExtraction
except ImportError:  # pragma: no cover - supports direct app/ test execution
    from app.config import EMBEDDING_DIMS, get_embeddings
    from app.prompts import MEMORY_EXTRACTION_PROMPT, MemoryExtraction

logger = logging.getLogger(__name__)


def get_user_memory_namespace(user_id: str) -> Tuple[str, str, str]:
    """
    Construct a strictly isolated namespace for a specific user.

    Ensures zero cross-tenant data leakage by prefixing with ('users', user_id, 'memories').
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id must be a non-empty string for memory isolation.")
    return ("users", user_id.strip(), "memories")


def retrieve_user_memories(
    store: Optional[BaseStore],
    user_id: str,
    query: str,
    top_k: int = 3,
) -> List[str]:
    """
    Retrieve relevant long-term memories for the specified user using semantic search.

    Args:
        store: LangGraph BaseStore instance.
        user_id: Current user identifier.
        query: User's current input message.
        top_k: Maximum number of memories to retrieve.

    Returns:
        List of memory content strings. Empty list if none found or on error.
    """
    if store is None:
        logger.warning(
            "memory.retrieve.skip reason=no_store user_id=%s query_chars=%d",
            user_id,
            len(query or ""),
        )
        return []

    if not user_id or not query:
        logger.info(
            "memory.retrieve.skip reason=missing_input user_id_present=%s query_chars=%d",
            bool(user_id),
            len(query or ""),
        )
        return []

    try:
        namespace = get_user_memory_namespace(user_id)
        logger.info(
            "memory.retrieve.start store=%s namespace=%s query_chars=%d top_k=%d",
            type(store).__name__,
            namespace,
            len(query),
            top_k,
        )
        search_results = store.search(namespace, query=query, limit=top_k)
        memories: List[str] = []
        for item in search_results:
            if isinstance(item.value, dict) and "content" in item.value:
                content = item.value["content"]
                if content and isinstance(content, str):
                    memories.append(content.strip())
        logger.info(
            "memory.retrieve.done count=%d user_id=%s top_k=%d",
            len(memories),
            user_id,
            top_k,
        )
        return memories
    except Exception as exc:
        # Graceful degradation: log error and return empty list, do not crash graph
        logger.error(
            "Failed to retrieve memories for user '%s': %s",
            user_id,
            exc,
            exc_info=True,
        )
        return []


def save_user_memory(
    store: Optional[BaseStore],
    user_id: str,
    memory_content: str,
    thread_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> bool:
    """
    Save an extracted memory item into the user's isolated Store namespace.

    Schema:
        {
            "content": memory_content,
            "source_thread_id": thread_id,
            "source_message_id": message_id,
            "created_at": ISO8601 UTC timestamp
        }
    """
    if store is None:
        logger.warning("memory.write.skip reason=no_store user_id=%s", user_id)
        return False

    if not user_id or not memory_content or not memory_content.strip():
        logger.info(
            "memory.write.skip reason=missing_input user_id_present=%s content_chars=%d",
            bool(user_id),
            len(memory_content or ""),
        )
        return False

    try:
        namespace = get_user_memory_namespace(user_id)
        memory_key = f"mem_{uuid4().hex[:12]}"
        payload: Dict[str, Any] = {
            "content": memory_content.strip(),
            "source_thread_id": thread_id,
            "source_message_id": message_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        store.put(
            namespace=namespace,
            key=memory_key,
            value=payload,
            index=["content"],
        )
        logger.info(
            "memory.write.done user_id=%s namespace=%s key=%s content_chars=%d",
            user_id,
            namespace,
            memory_key,
            len(memory_content.strip()),
        )
        return True
    except Exception as exc:
        logger.error(
            "Failed to write memory for user '%s': %s",
            user_id,
            exc,
            exc_info=True,
        )
        return False


def extract_and_save_memory(
    store: Optional[BaseStore],
    user_id: str,
    extraction_llm: Any,
    extraction_input: str,
    thread_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> bool:
    """Extract an eligible memory and persist it through the shared store path."""
    if not user_id or not extraction_input:
        logger.info(
            "memory.extract.skip reason=missing_input user_id_present=%s input_chars=%d",
            bool(user_id),
            len(extraction_input or ""),
        )
        return False

    try:
        logger.info(
            "memory.extract.start user_id=%s thread_id=%s input_chars=%d",
            user_id,
            thread_id,
            len(extraction_input),
        )
        extraction: MemoryExtraction = extraction_llm.invoke(
            [
                SystemMessage(content=MEMORY_EXTRACTION_PROMPT),
                HumanMessage(content=extraction_input),
            ]
        )
        logger.info(
            "memory.extract.done user_id=%s should_store=%s memory_chars=%d",
            user_id,
            extraction.should_store,
            len(extraction.memory or ""),
        )
        if not extraction.should_store or not extraction.memory:
            return False
        return save_user_memory(
            store=store,
            user_id=user_id,
            memory_content=extraction.memory,
            thread_id=thread_id,
            message_id=message_id,
        )
    except Exception as exc:
        logger.warning("Memory extraction failed for user '%s': %s", user_id, exc, exc_info=True)
        return False

def create_memory_store(
    embeddings: Optional[Union[Embeddings, Any]] = None,
    dims: int = EMBEDDING_DIMS,
) -> InMemoryStore:
    """
    Factory to create an InMemoryStore configured with semantic indexing.

    Args:
        embeddings: Embeddings instance or callable. If provided, semantic search is enabled.
        dims: Vector dimension for the embeddings index.
    """
    active_embeddings = embeddings or get_embeddings()
    logger.info(
        "memory.store.create store=InMemoryStore embedding=%s dims=%d fields=%s",
        type(active_embeddings).__name__,
        dims,
        ["content"],
    )
    index_cfg = IndexConfig(
        dims=dims,
        embed=active_embeddings,
        fields=["content"],
    )
    return InMemoryStore(index=index_cfg)

