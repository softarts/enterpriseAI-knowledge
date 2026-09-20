"""LangGraph workflow definition for Conversational Memory MVP V1."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from app import config as app_config
from app.memory import create_memory_store, extract_and_save_memory, retrieve_user_memories
from app.prompts import (
    MEMORY_EXTRACTION_PROMPT,
    MemoryExtraction,
    format_system_prompt_with_memories,
)
from app.state import MemoryGraphState

logger = logging.getLogger(__name__)


def create_retrieve_memory_node(top_k_default: int = app_config.DEFAULT_TOP_K):
    """Node 1: Retrieve long-term memories from LangGraph Store for the current user."""

    def retrieve_memory(
        state: MemoryGraphState,
        config: RunnableConfig,
        *,
        store: BaseStore,
    ) -> Dict[str, Any]:
        configurable = config.get("configurable", {})
        user_id: Optional[str] = configurable.get("user_id")
        top_k: int = configurable.get("top_k", top_k_default)

        messages = state.get("messages", [])
        if not messages or not user_id:
            return {"retrieved_memories": []}

        # Find the latest user query
        last_user_message: Optional[str] = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) or (
                hasattr(msg, "type") and msg.type == "human"
            ):
                last_user_message = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        if not last_user_message:
            return {"retrieved_memories": []}

        memories = retrieve_user_memories(
            store=store,
            user_id=user_id,
            query=last_user_message,
            top_k=top_k,
        )
        return {"retrieved_memories": memories}

    return retrieve_memory


def create_generate_response_node(llm: BaseChatModel):
    """Node 2: Generate response using LLM with short-term history and long-term memories."""

    def generate_response(
        state: MemoryGraphState,
        config: RunnableConfig,
    ) -> Dict[str, Any]:
        retrieved_memories: List[str] = state.get("retrieved_memories", [])
        system_prompt = format_system_prompt_with_memories(retrieved_memories)

        # Prepend system message to thread message history
        conversation_messages = [SystemMessage(content=system_prompt)] + list(
            state.get("messages", [])
        )

        response = llm.invoke(conversation_messages)
        return {"messages": [response]}

    return generate_response


def create_update_memory_node(llm: BaseChatModel):
    """Node 3: Extract and persist long-term memories using structured LLM output."""

    extraction_llm = llm.with_structured_output(MemoryExtraction)

    def update_memory(
        state: MemoryGraphState,
        config: RunnableConfig,
        *,
        store: BaseStore,
    ) -> Dict[str, Any]:
        configurable = config.get("configurable", {})
        user_id: Optional[str] = configurable.get("user_id")
        thread_id: Optional[str] = configurable.get("thread_id")

        if not user_id or store is None:
            return {}

        messages = state.get("messages", [])
        if not messages:
            return {}

        # Identify latest user message and its ID
        latest_user_content: Optional[str] = None
        latest_user_id: Optional[str] = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) or (
                hasattr(msg, "type") and msg.type == "human"
            ):
                latest_user_content = (
                    msg.content if isinstance(msg.content, str) else str(msg.content)
                )
                latest_user_id = getattr(msg, "id", None)
                break

        if not latest_user_content:
            return {}

        try:
            extract_and_save_memory(
                store=store,
                user_id=user_id,
                extraction_llm=extraction_llm,
                extraction_input=f"用户输入: {latest_user_content}",
                thread_id=thread_id,
                message_id=latest_user_id,
            )
        except Exception as exc:
            # Memory extraction or write failure is a non-critical error:
            # log and do not break conversational response
            logger.warning(
                "Memory extraction failed for user '%s': %s",
                user_id,
                exc,
                exc_info=True,
            )

        return {}

    return update_memory


def build_memory_graph(
    llm: Optional[BaseChatModel] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    store: Optional[BaseStore] = None,
    top_k: int = app_config.DEFAULT_TOP_K,
) -> CompiledStateGraph:
    """
    Construct and compile the LangGraph Memory workflow.

    Flow:
        START -> retrieve_memory -> generate_response -> update_memory -> END
    """
    active_llm = llm or app_config.get_chat_model()
    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()
    active_store = store if store is not None else create_memory_store(
        embeddings=app_config.get_embeddings(),
        dims=app_config.EMBEDDING_DIMS,
    )

    workflow = StateGraph(MemoryGraphState)

    # Register nodes
    workflow.add_node("retrieve_memory", create_retrieve_memory_node(top_k))
    workflow.add_node("generate_response", create_generate_response_node(active_llm))
    workflow.add_node("update_memory", create_update_memory_node(active_llm))

    # Define linear execution edges
    workflow.add_edge(START, "retrieve_memory")
    workflow.add_edge("retrieve_memory", "generate_response")
    workflow.add_edge("generate_response", "update_memory")
    workflow.add_edge("update_memory", END)

    return workflow.compile(checkpointer=active_checkpointer, store=active_store)
