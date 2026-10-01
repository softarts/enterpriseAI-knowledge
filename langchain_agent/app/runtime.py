"""Reusable LangGraph runtime: Checkpointer short-term + Store long-term memory."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.store.base import BaseStore

from . import config as app_config
from .graph import build_memory_agent_graph
from .long_memory import create_memory_store

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "default-user"
GRAPH_RECURSION_LIMIT = app_config.AGENT_MAX_STEPS_SYNC
RECURSION_LIMIT_ANSWER = (
    "这次请求需要过多的工具步骤，已安全停止。请缩小问题范围或拆成几个步骤再试。"
)


@dataclass
class MemoryContext:
    """Enterprise retrieval query and prior messages for one thread."""

    retrieval_query: str
    conversation_messages: List[BaseMessage]

    def format_with_enterprise_context(self, enterprise_context: str) -> str:
        return f"ENTERPRISE KNOWLEDGE:\n{enterprise_context}"


@dataclass
class MemoryRuntime:
    """Application-scoped Checkpointer (short-term) + Store (long-term).

    The store is created lazily on first use so that importing the runtime
    never loads the embedding model; inject a store for tests.
    """

    checkpointer: BaseCheckpointSaver
    store: Optional[BaseStore] = field(default=None)

    def get_store(self) -> BaseStore:
        if self.store is None:
            logger.info("memory.runtime.store.lazy_create")
            self.store = create_memory_store()
        return self.store

    def prepare_context(self, thread_id: Optional[str], question: str) -> MemoryContext:
        """Read prior messages for this thread; do not mutate checkpoint state."""
        conversation_messages: List[BaseMessage] = []
        checkpoint_found = False
        if thread_id:
            try:
                checkpoint_tuple = self.checkpointer.get_tuple(
                    {"configurable": {"thread_id": thread_id}}
                )
                if checkpoint_tuple is not None:
                    checkpoint_found = True
                    channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                    conversation_messages = list(channel_values.get("messages", []))
            except Exception:
                logger.warning(
                    "Short-term memory retrieval failed for thread_id=%s",
                    thread_id,
                    exc_info=True,
                )
        logger.info(
            "memory.checkpoint.read thread_id=%s found=%s message_count=%d message_types=%s",
            thread_id,
            checkpoint_found,
            len(conversation_messages),
            [
                getattr(message, "type", type(message).__name__)
                for message in conversation_messages
            ],
        )
        return MemoryContext(
            retrieval_query=question,
            conversation_messages=conversation_messages,
        )

    def generate_answer_with_memory(
        self,
        llm: BaseChatModel,
        system_prompt: str,
        question: str,
        thread_id: str,
        user_id: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> str:
        """Generate an answer and let the graph checkpoint messages by thread.

        Short-term history is restored by the bound Checkpointer; long-term
        memory is searched only if the agent calls the search_memory tool and
        is written by the update_memory node after the final answer.
        """
        active_user_id = user_id or DEFAULT_USER_ID
        active_top_k = top_k or app_config.MEMORY_TOP_K
        store = self.get_store()
        logger.info(
            "memory.graph.build thread_id=%s user_id=%s checkpointer=%s store=%s top_k=%d",
            thread_id,
            active_user_id,
            type(self.checkpointer).__name__,
            type(store).__name__,
            active_top_k,
        )
        answer_graph = build_memory_agent_graph(
            llm=llm,
            checkpointer=self.checkpointer,
            system_prompt=system_prompt,
            store=store,
        )
        logger.info(
            "memory.graph.invoke.start thread_id=%s input_message_count=1",
            thread_id,
        )
        try:
            result = answer_graph.invoke(
                {"messages": [HumanMessage(content=question)]},
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "user_id": active_user_id,
                        "top_k": active_top_k,
                    },
                    "metadata": {
                        "thread_id": thread_id,
                        "user_id": active_user_id,
                        "entrypoint": "chat_service.api.chat",
                    },
                    "tags": ["chat_service", "api-chat", "tool-agent"],
                    "recursion_limit": GRAPH_RECURSION_LIMIT,
                },
            )
        except GraphRecursionError:
            logger.warning(
                "memory.graph.invoke.recursion_limit thread_id=%s limit=%d",
                thread_id,
                GRAPH_RECURSION_LIMIT,
            )
            return RECURSION_LIMIT_ANSWER
        result_messages = result.get("messages", [])
        final_message = result_messages[-1]
        answer = getattr(final_message, "content", "")
        if not isinstance(answer, str):
            answer = "".join(
                block.get("text", "") for block in answer if isinstance(block, dict)
            )
        logger.info(
            "memory.graph.invoke.completed thread_id=%s result_message_count=%d answer_chars=%d",
            thread_id,
            len(result_messages),
            len(answer),
        )
        return answer


def create_memory_runtime(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    store: Optional[BaseStore] = None,
) -> MemoryRuntime:
    """Create an application-scoped short-term + long-term memory runtime."""
    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()
    logger.info(
        "memory.runtime.create checkpointer=%s store=%s",
        type(active_checkpointer).__name__,
        type(store).__name__ if store is not None else "lazy",
    )
    return MemoryRuntime(checkpointer=active_checkpointer, store=store)


_default_runtime: Optional[MemoryRuntime] = None


def get_default_memory_runtime() -> MemoryRuntime:
    """Return one process-scoped runtime for the default application path."""
    global _default_runtime
    if _default_runtime is None:
        logger.info("memory.runtime.default.create")
        _default_runtime = create_memory_runtime()
    else:
        logger.debug("memory.runtime.default.reuse")
    return _default_runtime
