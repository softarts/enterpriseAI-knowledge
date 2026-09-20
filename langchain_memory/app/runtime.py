"""Reusable LangGraph runtime for QA short- and long-term memory."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, List, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.store.base import BaseStore
from typing_extensions import Annotated

try:
    from . import config as app_config
    from .memory import create_memory_store, extract_and_save_memory, retrieve_user_memories
    from .prompts import MemoryExtraction
except ImportError:  # pragma: no cover - supports direct app/ test execution
    from app import config as app_config
    from app.memory import create_memory_store, extract_and_save_memory, retrieve_user_memories
    from app.prompts import MemoryExtraction

logger = logging.getLogger(__name__)


class ConversationState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]


@dataclass
class MemoryContext:
    """Prepared conversational context for one QA turn."""

    retrieval_query: str
    conversation_messages: List[BaseMessage]
    long_term_memories: List[str]

    def format_with_enterprise_context(self, enterprise_context: str) -> str:
        memory_text = "\n".join(f"- {memory}" for memory in self.long_term_memories)
        history_parts: List[str] = []
        for message in self.conversation_messages:
            message_type = getattr(message, "type", "message")
            role = "用户" if message_type == "human" else "助手"
            content = getattr(message, "content", "")
            if content:
                history_parts.append(f"{role}: {content}")
        history_text = "\n".join(history_parts) or "（当前 thread 尚无历史对话）"
        return (
            "USER MEMORY:\n"
            f"{memory_text or '（无相关用户记忆）'}\n\n"
            "SHORT-TERM CONVERSATION:\n"
            f"{history_text}\n\n"
            "ENTERPRISE KNOWLEDGE:\n"
            f"{enterprise_context}"
        )


@dataclass
class MemoryRuntime:
    """Application-scoped Store and Checkpointer dependencies."""

    store: BaseStore
    checkpointer: BaseCheckpointSaver
    conversation_graph: object

    def prepare_context(
        self,
        user_id: Optional[str],
        thread_id: Optional[str],
        question: str,
        top_k: int = app_config.DEFAULT_TOP_K,
    ) -> MemoryContext:
        """Prepare thread history, long-term memories, and retrieval query."""
        logger.info(
            "memory.prepare.start user_id=%s thread_id=%s question_chars=%d top_k=%d store=%s",
            user_id,
            thread_id,
            len(question or ""),
            top_k,
            type(self.store).__name__,
        )
        conversation_messages: List[BaseMessage] = []
        if thread_id:
            try:
                conversation_messages = self.get_thread_messages(thread_id)
            except Exception:
                logger.warning("Short-term memory retrieval failed", exc_info=True)

        retrieval_query = question
        if thread_id:
            try:
                retrieval_query = self.build_retrieval_query(thread_id, question)
            except Exception:
                logger.warning(
                    "Retrieval query rewrite failed; using current question",
                    exc_info=True,
                )

        long_term_memories: List[str] = []
        if user_id:
            try:
                long_term_memories = retrieve_user_memories(
                    store=self.store,
                    user_id=user_id,
                    query=retrieval_query,
                    top_k=top_k,
                )
            except Exception:
                logger.warning("Long-term memory retrieval failed", exc_info=True)
        else:
            logger.info(
                "memory.retrieve.skip reason=no_user_id thread_id=%s; long-term memory is disabled for this request",
                thread_id,
            )

        context = MemoryContext(
            retrieval_query=retrieval_query,
            conversation_messages=conversation_messages,
            long_term_memories=long_term_memories,
        )
        logger.info(
            "memory.prepare.done user_id=%s thread_id=%s short_term_messages=%d long_term_memories=%d query_chars=%d",
            user_id,
            thread_id,
            len(conversation_messages),
            len(long_term_memories),
            len(retrieval_query),
        )
        return context

    def record_turn(
        self,
        user_id: Optional[str],
        thread_id: Optional[str],
        question: str,
        answer: str,
    ) -> None:
        """Persist short-term turn and extract eligible long-term memory."""
        logger.info(
            "memory.record.start user_id=%s thread_id=%s question_chars=%d answer_chars=%d",
            user_id,
            thread_id,
            len(question or ""),
            len(answer or ""),
        )
        history = self.get_thread_messages(thread_id) if thread_id else []

        if thread_id:
            try:
                self.append_turn(
                    thread_id,
                    HumanMessage(content=question),
                    AIMessage(content=answer),
                )
            except Exception:
                logger.warning("Short-term memory write failed", exc_info=True)

        if not user_id:
            logger.info("memory.record.done reason=no_user_id thread_id=%s", thread_id)
            return

        try:
            history_text = self._format_conversation_history(history)
            extraction_input = (
                f"当前 thread context:\n{history_text or '（无）'}\n\n"
                f"当前用户消息:\n{question}\n\n"
                f"当前助手回答:\n{answer}"
            )
            extraction_llm = app_config.get_chat_model().with_structured_output(MemoryExtraction)
            extract_and_save_memory(
                store=self.store,
                user_id=user_id,
                extraction_llm=extraction_llm,
                extraction_input=extraction_input,
                thread_id=thread_id,
            )
        except Exception:
            logger.warning("Memory extraction or write failed", exc_info=True)
        logger.info("memory.record.done user_id=%s thread_id=%s", user_id, thread_id)

    @staticmethod
    def _format_conversation_history(messages: List[BaseMessage]) -> str:
        parts: List[str] = []
        for message in messages:
            message_type = getattr(message, "type", "message")
            role = "用户" if message_type == "human" else "助手"
            content = getattr(message, "content", "")
            if content:
                parts.append(f"{role}: {content}")
        return "\n".join(parts)

    def build_retrieval_query(self, thread_id: str, question: str) -> str:
        """Build a standalone retrieval query from the current thread history."""
        config = {"configurable": {"thread_id": thread_id}}
        state = self.conversation_graph.get_state(config)
        values = state.values if state else {}
        messages = list(values.get("messages", []))

        previous_questions: List[str] = []
        for message in messages[-6:]:
            if getattr(message, "type", "") != "human":
                continue
            content = str(getattr(message, "content", "")).strip()
            if content:
                previous_questions.append(content)

        if not previous_questions:
            logger.info(
                "memory.query_rewrite.done thread_id=%s previous_questions=0 query_chars=%d",
                thread_id,
                len(question),
            )
            return question

        normalized_question = " ".join(question.split()).casefold()
        distinct_previous = []
        for previous_question in previous_questions:
            normalized_previous = " ".join(previous_question.split()).casefold()
            if normalized_previous != normalized_question:
                distinct_previous.append(previous_question)
        question_prefix = normalized_question[:40]
        follow_up_prefixes = ("how about", "what about", "and ", "then ")
        is_short_follow_up = len(question.split()) <= 8
        is_prefixed_follow_up = question_prefix.startswith(follow_up_prefixes)
        selected_questions = (
            distinct_previous[-2:]
            if is_short_follow_up or is_prefixed_follow_up
            else []
        )
        retrieval_query = "\n".join(selected_questions + [question])
        logger.info(
            "memory.query_rewrite.done thread_id=%s previous_questions=%d selected_questions=%d follow_up=%s query_chars=%d",
            thread_id,
            len(previous_questions),
            len(selected_questions),
            bool(selected_questions),
            len(retrieval_query),
        )
        return retrieval_query

    def get_thread_messages(self, thread_id: str) -> List[BaseMessage]:
        logger.info("memory.short_term.read.start thread_id=%s", thread_id)
        config = {"configurable": {"thread_id": thread_id}}
        state = self.conversation_graph.get_state(config)
        values = state.values if state else {}
        messages = list(values.get("messages", []))
        logger.info(
            "memory.short_term.read.done thread_id=%s messages=%d",
            thread_id,
            len(messages),
        )
        return messages

    def append_turn(
        self,
        thread_id: str,
        user_message: BaseMessage,
        assistant_message: BaseMessage,
    ) -> None:
        logger.info(
            "memory.short_term.append.start thread_id=%s user_chars=%d assistant_chars=%d",
            thread_id,
            len(getattr(user_message, "content", "")),
            len(getattr(assistant_message, "content", "")),
        )
        config = {"configurable": {"thread_id": thread_id}}
        self.conversation_graph.invoke(
            {"messages": [user_message, assistant_message]},
            config=config,
        )
        logger.info("memory.short_term.append.done thread_id=%s", thread_id)


def create_memory_runtime(
    store: Optional[BaseStore] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> MemoryRuntime:
    active_store = (
        store
        if store is not None
        else create_memory_store(
            embeddings=app_config.get_embeddings(),
            dims=app_config.EMBEDDING_DIMS,
        )
    )
    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()

    logger.info(
        "memory.runtime.create store=%s checkpointer=%s embedding=%s dims=%d",
        type(active_store).__name__,
        type(active_checkpointer).__name__,
        type(getattr(active_store, "index", None)).__name__,
        app_config.EMBEDDING_DIMS,
    )

    workflow = StateGraph(ConversationState)
    workflow.add_node("record_turn", lambda state: {})
    workflow.add_edge(START, "record_turn")
    workflow.add_edge("record_turn", END)
    conversation_graph = workflow.compile(checkpointer=active_checkpointer)

    return MemoryRuntime(
        store=active_store,
        checkpointer=active_checkpointer,
        conversation_graph=conversation_graph,
    )


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
