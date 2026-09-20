"""
qa_service.pipeline — 问答主入口。

流程：
    1. retrieval.retrieve(question)         向量检索 Top-K chunk
    2. retrieval.is_confident(chunks)       置信度阈值判断
       不通过 → 直接返回"未找到相关信息"，不调用 LLM
    3. prompt_builder.build_context(chunks) 组装 context 字符串
    4. 把 context 渲染进 SYSTEM_PROMPT
    5. llm_client.generate(...)             LangChain LCEL chain 调用 LLM
    6. reflection.reflect(...)              Reflection 评审
    7. 返回 AnswerResult
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from chat_service.trace import TraceBuilder
from qa_service import config, llm_client, prompt_builder, reflection, retrieval, revision
from qa_service.models import AnswerResult

logger = logging.getLogger(__name__)

_NOT_FOUND_ANSWER = "根据现有知识库内容，未能找到与该问题相关的信息。"


def answer_question(
    question: str,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    memory_runtime: Optional[Any] = None,
) -> AnswerResult:
    """
    对用户问题执行单次检索 + 单次生成，返回最终答案。

    Args:
        question: 用户输入的自然语言问题。
        user_id: 用户级长期 memory namespace。
        thread_id: LangGraph Checkpointer 使用的短期对话 thread。
        memory_runtime: 可注入的 application-scoped MemoryRuntime。

    Returns:
        AnswerResult:
            answer           — 最终呈现给用户的文本
            sources          — 检索到的 chunk_id 列表（未找到时为空列表）
            passed_reflection — Reflection 校验结果（未找到时为 None）
    """
    question = (question or "").strip()
    if memory_runtime is None and (user_id or thread_id):
        try:
            from langchain_memory import get_default_memory_runtime

            memory_runtime = get_default_memory_runtime()
        except Exception:
            logger.warning("Memory runtime initialization failed", exc_info=True)

    from langchain_memory import MemoryContext

    if memory_runtime is not None:
        memory_context = memory_runtime.prepare_context(
            user_id=user_id,
            thread_id=thread_id,
            question=question,
            top_k=config.TOP_K,
        )
    else:
        memory_context = MemoryContext(
            retrieval_query=question,
            conversation_messages=[],
            long_term_memories=[],
        )

    trace = TraceBuilder()
    trace.add_step(
        "memory",
        {
            "enabled": memory_runtime is not None,
            "user_id_present": bool(user_id),
            "thread_id_present": bool(thread_id),
            "store_type": type(memory_runtime.store).__name__ if memory_runtime is not None else None,
            "retrieval_query": memory_context.retrieval_query,
            "user_memories": len(memory_context.long_term_memories),
            "short_term_messages": len(memory_context.conversation_messages),
        },
        status="ok" if memory_runtime is not None else "skipped",
    )
    trace.add_step(
        "request",
        {"question": question, "question_chars": len(question), "top_k": config.TOP_K},
        status="ok" if question else "error",
    )
    if not question:
        logger.warning("answer_question() called with empty question")
        answer = AnswerResult(
            answer=_NOT_FOUND_ANSWER, sources=[], passed_reflection=None
        )
        trace.add_step("response", {"answer_chars": len(answer.answer), "sources": []})
        answer.trace = trace.build()
        return answer

    # Step 1: 向量检索
    retrieval_started = time.perf_counter()
    logger.info(
        "qa.retrieval.start memory_enabled=%s user_id_present=%s thread_id_present=%s query_chars=%d",
        memory_runtime is not None,
        bool(user_id),
        bool(thread_id),
        len(memory_context.retrieval_query),
    )

    chunks = retrieval.retrieve(memory_context.retrieval_query, k=config.TOP_K)
    trace.add_step(
        "retrieval",
        {
            "query": memory_context.retrieval_query,
            "top_k": config.TOP_K,
            "count": len(chunks),
            "top_distance": chunks[0].distance if chunks else None,
            "chunks": [
                {
                    "rank": c.rank,
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "source_path": c.source_path,
                    "heading": c.heading,
                    "distance": c.distance,
                }
                for c in chunks
            ],
        },
        duration_ms=(time.perf_counter() - retrieval_started) * 1000,
    )

    # Step 2: 置信度判断
    confident = retrieval.is_confident(chunks, threshold=config.CONFIDENCE_THRESHOLD)
    trace.add_step(
        "confidence",
        {
            "passed": confident,
            "threshold": config.CONFIDENCE_THRESHOLD,
            "top_distance": chunks[0].distance if chunks else None,
        },
    )
    if not confident:
        logger.info("Confidence check failed; returning not-found answer")
        answer = AnswerResult(answer=_NOT_FOUND_ANSWER, sources=[], passed_reflection=None)
        trace.add_step(
            "response", {"answer_chars": len(answer.answer), "sources": [], "llm_called": False}
        )
        answer.trace = trace.build()
        return answer

    # Step 3: 组装 enterprise context and optional conversational context.
    enterprise_context = prompt_builder.build_context(chunks)
    context = memory_context.format_with_enterprise_context(enterprise_context)
    trace.add_step(
        "context",
        {
            "chars": len(context),
            "enterprise_chars": len(enterprise_context),
            "chunks": len(chunks),
            "memory_enabled": memory_runtime is not None,
            "user_id_present": bool(user_id),
            "thread_id_present": bool(thread_id),
            "user_memories": len(memory_context.long_term_memories),
            "short_term_messages": len(memory_context.conversation_messages),
        },
    )

    # Step 4: 渲染 system prompt（把 context 填入 SYSTEM_PROMPT 的 {context} 占位符）
    system_prompt = prompt_builder.SYSTEM_PROMPT.format(context=context)

    # Step 5: 调用 LLM
    llm_started = time.perf_counter()
    draft_answer = llm_client.generate(system_prompt, context, question)
    trace.add_step(
        "llm",
        {
            # ── Request / Input ─────────────────────────────────────────
            "model": config.LLM_MODEL,
            "max_tokens": config.LLM_MAX_TOKENS,
            "thinking_enabled": config.LLM_ENABLE_THINKING,
            "question_chars": len(question),
            "context_chars": len(context),
            # ── Raw Generation Output ────────────────────────────────────
            # Full unmodified string returned by llm_client.generate().
            # draft_answer may later be overwritten by Revision; this field
            # always preserves the original LLM response for diagnostics.
            "raw_output": draft_answer,
            # ── Metadata ─────────────────────────────────────────────────
            "answer_chars": len(draft_answer),
        },
        duration_ms=(time.perf_counter() - llm_started) * 1000,
    )

    # Step 6: Reflection & Revision Closed Loop
    revised_answer: Optional[str] = None
    passed_reflection: Optional[bool] = None

    if not config.is_reflection_enabled():
        final_answer = draft_answer
        output_source = "generation"
        final_status = "success"

        trace.add_step(
            "reflection",
            {
                "enabled": False,
                "status": "skipped",
                "decision": None,
                "model": None,
                "model_source": None,
                "prompt": None,
                "input": None,
                "output": None,
                "parsed_result": None,
                "reasons": [],
                "unnecessary_content": [],
                "missing_information": [],
                "unsupported_claims": [],
                "error": None,
            },
            status="skipped",
        )
        trace.add_step(
            "revision",
            {
                "executed": False,
                "status": "skipped",
                "model": None,
                "prompt": None,
                "input": None,
                "output": None,
                "error": None,
            },
            status="skipped",
        )
    else:
        reflection_result = reflection.reflect(
            question=question,
            context=enterprise_context,
            draft_answer=draft_answer,
            retrieved_chunks=chunks,
        )
        passed_reflection = reflection_result.passed
        parsed_dict = (
            reflection_result.parsed_result.to_dict()
            if reflection_result.parsed_result
            else None
        )

        trace.add_step(
            "reflection",
            {
                "enabled": True,
                "status": reflection_result.status,
                "model": reflection_result.model,
                "model_source": reflection_result.model_source,
                "prompt": reflection_result.prompt,
                "input": {
                    "question": question,
                    "context": context,
                    "answer": draft_answer,
                },
                "output": reflection_result.raw_output,
                "parsed_result": parsed_dict,
                "decision": reflection_result.decision,
                "reasons": (
                    reflection_result.parsed_result.reasons
                    if reflection_result.parsed_result
                    else []
                ),
                "unnecessary_content": (
                    reflection_result.parsed_result.unnecessary_content
                    if reflection_result.parsed_result
                    else []
                ),
                "missing_information": (
                    reflection_result.parsed_result.missing_information
                    if reflection_result.parsed_result
                    else []
                ),
                "unsupported_claims": (
                    reflection_result.parsed_result.unsupported_claims
                    if reflection_result.parsed_result
                    else []
                ),
                "error": reflection_result.error,
            },
            status="ok" if reflection_result.status == "success" else "error",
            duration_ms=reflection_result.duration_ms,
        )

        if reflection_result.status == "success" and reflection_result.decision == "REVISE":
            revision_result = revision.revise(
                question=question,
                context=enterprise_context,
                draft_answer=draft_answer,
                reflection_result=reflection_result,
            )
            trace.add_step(
                "revision",
                {
                    "executed": True,
                    "status": revision_result.status,
                    "model": revision_result.model,
                    "prompt": revision_result.prompt,
                    "input": revision_result.input,
                    "output": revision_result.output,
                    "error": revision_result.error,
                },
                status="ok" if revision_result.status == "success" else "error",
                duration_ms=revision_result.duration_ms,
            )

            if revision_result.status == "success" and revision_result.revised_answer:
                revised_answer = revision_result.revised_answer
                final_answer = revision_result.revised_answer
                output_source = "revision"
                final_status = "success"
            else:
                # Revision 失败：回退到 draft_answer
                final_answer = draft_answer
                output_source = "generation"
                final_status = "success"
        else:
            # PASS 或 Reflection 异常：保留 draft_answer，跳过 revision
            final_answer = draft_answer
            output_source = "generation"
            final_status = "success"
            trace.add_step(
                "revision",
                {
                    "executed": False,
                    "status": "skipped",
                    "model": None,
                    "prompt": None,
                    "input": None,
                    "output": None,
                    "error": None,
                },
                status="skipped",
            )

    trace.add_step(
        "final_output",
        {
            "answer": final_answer,
            "source": output_source,
            "status": final_status,
            "draft_answer": draft_answer,
            "revised_answer": revised_answer,
        },
        status="ok",
    )

    answer = AnswerResult(
        answer=final_answer,
        sources=[c.chunk_id for c in chunks],
        passed_reflection=passed_reflection,
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

    if memory_runtime is not None:
        memory_runtime.record_turn(
            user_id=user_id,
            thread_id=thread_id,
            question=question,
            answer=final_answer,
        )
    return answer

