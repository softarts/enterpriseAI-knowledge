"""
ChatService — orchestrates a single Ask turn and produces the trace.

Current (v1) flow:
    question -> [request step] -> HuggingFaceLLM.chat() -> [llm step]
             -> [response step] -> ChatResult(answer, trace)

The retrieval seam for the NEXT stage is marked explicitly below. When RAG is
added, `vector_service.search(question, top_k)` will run BEFORE the LLM call,
its results become a "retrieval" trace step, and the retrieved context is
prepended to the prompt. Nothing about the public API or the trace shape needs
to change for that — retrieval simply adds a step. It is intentionally NOT
implemented here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from chat_service.config import settings
from chat_service.llm.hf_client import HFTokenMissingError, HuggingFaceLLM
from chat_service.trace import TraceBuilder


@dataclass
class ChatResult:
    """Internal result carried back to the route layer."""

    answer: str = ""
    trace: Dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class ChatService:
    """Coordinates the LLM call and trace assembly for one question."""

    def __init__(self, llm: HuggingFaceLLM | None = None) -> None:
        self._llm = llm or HuggingFaceLLM()

    def ask(self, question: str) -> ChatResult:
        """Run the Ask flow for a single question and return answer + trace."""
        trace = TraceBuilder()

        question = (question or "").strip()

        # ---- Step 1: request -------------------------------------------------
        trace.add_step(
            name="request",
            detail={
                "question": question,
                "question_chars": len(question),
                "model": settings.model,
                "max_tokens": settings.max_tokens,
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

        # ---- (FUTURE) Step: retrieval ---------------------------------------
        # RAG SEAM — not implemented in v1.
        # When enabling RAG:
        #   from vector_service...  # or a RetrievalClient abstraction
        #   hits = retriever.search(question, top_k=...)
        #   trace.add_step("retrieval", {"top_k": ..., "results": [...]})
        #   context = assemble_context(hits)
        #   trace.add_step("context", {"chunks": ..., "chars": ...})
        # The assembled context would then be passed into the LLM prompt below.

        # ---- Step 2: llm -----------------------------------------------------
        started = time.perf_counter()
        try:
            llm_out = self._llm.chat(question)
        except HFTokenMissingError as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            trace.add_step(
                name="llm",
                detail={"error_type": "config", "message": str(exc)},
                status="error",
                duration_ms=duration_ms,
            )
            trace.add_step(
                name="response",
                detail={"answer_chars": 0},
                status="error",
            )
            return ChatResult(answer="", trace=trace.build(), error=str(exc))
        except Exception as exc:  # noqa: BLE001 - surface any HF/network error to UI
            duration_ms = (time.perf_counter() - started) * 1000
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
        answer = llm_out["answer"]
        trace.add_step(
            name="llm",
            detail={
                "provider": "huggingface",
                "model": llm_out["model"],
                "max_tokens": llm_out["max_tokens"],
                "finish_reason": llm_out["finish_reason"],
                "usage": llm_out["usage"],
            },
            status="ok",
            duration_ms=duration_ms,
        )

        # ---- Step 3: response ------------------------------------------------
        trace.add_step(
            name="response",
            detail={"answer_chars": len(answer)},
            status="ok",
        )

        return ChatResult(answer=answer, trace=trace.build(), error=None)
