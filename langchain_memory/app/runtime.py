"""Reusable LangGraph runtime for Checkpointer-backed short-term memory."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

try:
    from . import config as app_config
    from .graph import build_memory_agent_graph
except ImportError:  # pragma: no cover - supports direct app/ test execution
    from app import config as app_config
    from app.graph import build_memory_agent_graph

logger = logging.getLogger(__name__)


@dataclass
class MemoryContext:
    """Enterprise retrieval query and prior messages for one thread."""

    retrieval_query: str
    conversation_messages: List[BaseMessage]

    def format_with_enterprise_context(self, enterprise_context: str) -> str:
        return f"ENTERPRISE KNOWLEDGE:\n{enterprise_context}"


@dataclass
class MemoryRuntime:
    """Application-scoped Checkpointer for short-term conversation state."""

    checkpointer: BaseCheckpointSaver

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
    ) -> str:
        """Generate an answer and let the graph checkpoint messages by thread."""
        logger.info(
            "memory.graph.build thread_id=%s checkpointer=%s",
            thread_id,
            type(self.checkpointer).__name__,
        )
        answer_graph = build_memory_agent_graph(
            llm=llm,
            checkpointer=self.checkpointer,
            system_prompt=system_prompt,
        )
        logger.info(
            "memory.graph.invoke.start thread_id=%s input_message_count=1",
            thread_id,
        )
        result = answer_graph.invoke(
            {"messages": [HumanMessage(content=question)]},
            config={"configurable": {"thread_id": thread_id}},
        )
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
) -> MemoryRuntime:
    """Create an application-scoped short-term memory runtime."""
    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()
    logger.info(
        "memory.runtime.create checkpointer=%s",
        type(active_checkpointer).__name__,
    )
    return MemoryRuntime(checkpointer=active_checkpointer)


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
