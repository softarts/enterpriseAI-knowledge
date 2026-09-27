"""Pure-chat pipeline backed by LangGraph short-term memory."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from chat_service.trace import TraceBuilder
from langchain_memory.app.runtime import MemoryRuntime
from qa_service import config as qa_config
from qa_service import llm_client

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    """Internal result carried back to the route layer."""

    answer: str = ""
    trace: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class ChatService:
    """Coordinates a pure chat answer and its thread-scoped checkpoint."""

    def __init__(self, memory_runtime: MemoryRuntime) -> None:
        self._memory_runtime = memory_runtime

    def ask(
        self,
        question: str,
        thread_id: str,
        user_id: Optional[str] = None,
    ) -> ChatResult:
        """Generate a chat answer using history checkpointed under ``thread_id``.

        Short-term history is restored by the Checkpointer; long-term memory
        is searched only when the agent decides to call its search tool, and
        written by the graph's update_memory node after the final answer.
        """
        trace = TraceBuilder()
        question = (question or "").strip()
        model_config = llm_client.get_model_config()
        memory_context = self._memory_runtime.prepare_context(
            thread_id=thread_id,
            question=question,
        )
        trace.add_step(
            name="request",
            detail={
                "question": question,
                "question_chars": len(question),
                "thread_id_present": bool(thread_id),
                "user_id_present": bool(user_id),
                "checkpoint_messages_before": len(memory_context.conversation_messages),
                "model": model_config["model"],
                "max_tokens": model_config["max_tokens"],
            },
            status="ok" if question else "error",
        )

        if not question:
            trace.add_step(
                name="response",
                detail={"answer_chars": 0, "reason": "empty question"},
                status="error",
            )
            return ChatResult(
                answer="",
                trace=trace.build(),
                error="Question must not be empty.",
            )

        started = time.perf_counter()
        logger.info(
            "chat.memory.call.start thread_id=%s question_chars=%d checkpoint_messages=%d",
            thread_id,
            len(question),
            len(memory_context.conversation_messages),
        )
        try:
            answer = self._memory_runtime.generate_answer_with_memory(
                llm=llm_client.get_llm(),
                system_prompt="",
                question=question,
                thread_id=thread_id,
                user_id=user_id,
            )
        except Exception as exc:  # noqa: BLE001 - return provider/config errors to UI
            duration_ms = (time.perf_counter() - started) * 1000
            logger.warning(
                "chat.memory.call.failed thread_id=%s error_type=%s duration_ms=%.2f",
                thread_id,
                type(exc).__name__,
                duration_ms,
            )
            message = f"{type(exc).__name__}: {exc}"
            trace.add_step(
                name="llm",
                detail={"error_type": "upstream", "message": message},
                status="error",
                duration_ms=duration_ms,
            )
            trace.add_step(
                name="response",
                detail={"answer_chars": 0},
                status="error",
            )
            return ChatResult(
                answer="",
                trace=trace.build(),
                error=f"LLM request failed: {message}",
            )

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "chat.memory.call.completed thread_id=%s answer_chars=%d duration_ms=%.2f",
            thread_id,
            len(answer),
            duration_ms,
        )
        trace.add_step(
            name="llm",
            detail={
                "provider": "openai-compatible",
                "model": model_config["model"],
                "max_tokens": model_config["max_tokens"],
                "thinking_enabled": qa_config.LLM_ENABLE_THINKING,
            },
            status="ok",
            duration_ms=duration_ms,
        )
        trace.add_step(
            name="response",
            detail={"answer": answer, "answer_chars": len(answer)},
            status="ok",
        )
        return ChatResult(answer=answer, trace=trace.build(), error=None)
