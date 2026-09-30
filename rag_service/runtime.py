"""rag_service.runtime — 对外问答入口，持有 Checkpointer + Store。

替代 qa_service.pipeline.answer_question() 中的手写 memory_runtime 逻辑：
短期对话历史由编译进图的 Checkpointer 按 thread_id 自动恢复与保存；
长期记忆由 Store + search_memory 工具 + update_memory 节点管理。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.store.base import BaseStore

from chat_service.trace import TraceBuilder
from langchain_agent.app import config as agent_config
from langchain_agent.app.long_memory import create_memory_store
from langchain_agent.app.runtime import DEFAULT_USER_ID

from rag_service import config, llm_client
from rag_service.graph import build_rag_graph
from rag_service.models import AnswerResult

logger = logging.getLogger(__name__)


@dataclass
class RagRuntime:
    """Application-scoped RAG runtime：Checkpointer（短期）+ Store（长期）。

    store 懒加载，避免 import 时加载 embedding 模型；测试中可注入
    InMemoryStore 与 fake llm。
    """

    checkpointer: BaseCheckpointSaver = field(default_factory=MemorySaver)
    store: Optional[BaseStore] = None

    def get_store(self) -> BaseStore:
        if self.store is None:
            logger.info("rag.runtime.store.lazy_create")
            self.store = create_memory_store()
        return self.store

    def answer_question(
        self,
        question: str,
        thread_id: Optional[str] = None,
        user_id: Optional[str] = None,
        llm: Optional[BaseChatModel] = None,
        top_k: Optional[int] = None,
    ) -> AnswerResult:
        """执行一次 RAG 问答（retrieve → generate → critic ↔ revise → finalize）。

        Args:
            question: 用户问题。
            thread_id: 短期记忆 thread；None 时使用一次性 thread（不累积历史）。
            user_id:  长期记忆命名空间；None 时使用 DEFAULT_USER_ID。
            llm:      可注入的聊天模型（测试用）；默认 rag_service.llm_client。
            top_k:    search_memory 工具的长期记忆返回条数。

        Returns:
            AnswerResult(answer, sources, passed_reflection, trace)，契约与
            qa_service.pipeline.answer_question() 相同。
        """
        question = (question or "").strip()
        trace = TraceBuilder()
        active_thread_id = thread_id or f"rag-once-{uuid.uuid4().hex}"

        trace.add_step(
            "short_term_memory",
            {
                "enabled": True,
                "thread_id_present": bool(thread_id),
                "managed_by": "langgraph_checkpointer",
            },
        )
        trace.add_step(
            "request",
            {
                "question": question,
                "question_chars": len(question),
                "top_k": config.TOP_K,
            },
            status="ok" if question else "error",
        )
        if not question:
            logger.warning("answer_question() called with empty question")
            answer = AnswerResult(
                answer=config.NOT_FOUND_ANSWER, sources=[], passed_reflection=None
            )
            trace.add_step(
                "response", {"answer_chars": len(answer.answer), "sources": []}
            )
            answer.trace = trace.build()
            return answer

        graph = build_rag_graph(
            llm=llm,
            checkpointer=self.checkpointer,
            store=self.get_store(),
        )
        logger.info(
            "rag.graph.invoke.start thread_id=%s user_id=%s question_chars=%d",
            active_thread_id,
            user_id or DEFAULT_USER_ID,
            len(question),
        )
        try:
            result = graph.invoke(
                {
                    "messages": [HumanMessage(content=question)],
                    "question": question,
                },
                config={
                    "configurable": {
                        "thread_id": active_thread_id,
                        "user_id": user_id or DEFAULT_USER_ID,
                        "top_k": top_k or agent_config.MEMORY_TOP_K,
                    },
                    "metadata": {
                        "thread_id": active_thread_id,
                        "user_id": user_id or DEFAULT_USER_ID,
                        "entrypoint": "rag_service.runtime.answer_question",
                    },
                    "tags": ["rag_service", "rag-agent"],
                    "recursion_limit": config.GRAPH_RECURSION_LIMIT,
                },
            )
        except GraphRecursionError:
            logger.warning(
                "rag.graph.invoke.recursion_limit thread_id=%s limit=%d",
                active_thread_id,
                config.GRAPH_RECURSION_LIMIT,
            )
            answer = AnswerResult(
                answer=config.RECURSION_LIMIT_ANSWER, sources=[], passed_reflection=None
            )
            trace.add_step(
                "response",
                {
                    "answer_chars": len(answer.answer),
                    "sources": [],
                    "recursion_limit_hit": True,
                },
                status="error",
            )
            answer.trace = trace.build()
            return answer

        for step in result.get("trace_steps", []):
            detail: Dict[str, Any] = step.get("detail", {})
            trace.add_step(
                step["name"],
                detail,
                status=step.get("status", "ok"),
                duration_ms=step.get("duration_ms"),
            )

        answer = AnswerResult(
            answer=result.get("final_answer", ""),
            sources=list(result.get("sources", [])),
            passed_reflection=result.get("passed_reflection"),
        )
        trace.add_step(
            "response",
            {
                "answer_chars": len(answer.answer),
                "sources": answer.sources,
                "passed_reflection": answer.passed_reflection,
            },
        )
        answer.trace = trace.build()
        logger.info(
            "rag.graph.invoke.completed thread_id=%s answer_chars=%d sources=%d",
            active_thread_id,
            len(answer.answer),
            len(answer.sources),
        )
        return answer


_default_runtime: Optional[RagRuntime] = None


def get_default_runtime() -> RagRuntime:
    """进程级默认 runtime（MemorySaver + 懒加载长期记忆 Store）。"""
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = RagRuntime()
    return _default_runtime


def answer_question(
    question: str,
    thread_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> AnswerResult:
    """qa_service.pipeline.answer_question() 的 LangGraph 原生替代入口。"""
    return get_default_runtime().answer_question(
        question=question,
        thread_id=thread_id,
        user_id=user_id,
    )
