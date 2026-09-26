"""Reusable LangGraph runtime for QA short- and long-term memory."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import List, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from typing_extensions import Annotated

try:
    from . import config as app_config
    from .graph import build_memory_agent_graph
    from .memory import create_memory_store, create_search_memory_tool, extract_and_save_memory
    from .prompts import MemoryExtraction
except ImportError:  # pragma: no cover - supports direct app/ test execution
    from app import config as app_config
    from app.graph import build_memory_agent_graph
    from app.memory import create_memory_store, create_search_memory_tool, extract_and_save_memory
    from app.prompts import MemoryExtraction

logger = logging.getLogger(__name__)


class ConversationState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]


@dataclass
class MemoryContext:
    """Prepared conversational context for one QA turn."""

    retrieval_query: str
    conversation_messages: List[BaseMessage]

    def format_with_enterprise_context(self, enterprise_context: str) -> str:
        history_parts: List[str] = []
        for message in self.conversation_messages:
            message_type = getattr(message, "type", "message")
            role = "用户" if message_type == "human" else "助手"
            content = getattr(message, "content", "")
            if content:
                history_parts.append(f"{role}: {content}")
        history_text = "\n".join(history_parts) or "（当前 thread 尚无历史对话）"
        return (
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
    _answer_llm: Optional[BaseChatModel] = field(default=None, init=False, repr=False)
    _answer_graph: Optional[CompiledStateGraph] = field(default=None, init=False, repr=False)

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

        # Enterprise KB retrieval always uses the raw current question: no
        # string-heuristic query rewriting is applied here.
        retrieval_query = question

        context = MemoryContext(
            retrieval_query=retrieval_query,
            conversation_messages=conversation_messages,
        )
        logger.info(
            "memory.prepare.done user_id=%s thread_id=%s short_term_messages=%d query_chars=%d",
            user_id,
            thread_id,
            len(conversation_messages),
            len(retrieval_query),
        )
        return context

    def generate_answer_with_memory(
        self,
        llm: BaseChatModel,
        system_prompt: str,
        question: str,
        user_id: str,
        top_k: int,
    ) -> str:
        """Generate the QA answer with `search_memory` in the same agent loop."""
        logger.info(
            "memory.answer_agent.start user_id=%s question_chars=%d",
            user_id,
            len(question),
        )
        if self._answer_graph is None or self._answer_llm is not llm:
            search_memory_tool = create_search_memory_tool(top_k)
            self._answer_graph = build_memory_agent_graph(
                llm=llm,
                store=self.store,
                tools=[search_memory_tool],
            )
            self._answer_llm = llm

        result = self._answer_graph.invoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=question),
                ]
            },
            config={
                "configurable": {
                    "user_id": user_id,
                    "top_k": top_k,
                }
            },
        )
        final_message = result.get("messages", [])[-1]
        answer = getattr(final_message, "content", "")
        if not isinstance(answer, str):
            answer = "".join(
                block.get("text", "") for block in answer if isinstance(block, dict)
            )
        logger.info(
            "memory.answer_agent.done user_id=%s answer_chars=%d",
            user_id,
            len(answer),
        )
        return answer

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

