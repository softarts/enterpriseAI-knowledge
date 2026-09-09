"""
qa_service.pipeline — 问答主入口。

流程：
    1. retrieval.retrieve(question)         向量检索 Top-K chunk
    2. retrieval.is_confident(chunks)       置信度阈值判断
       不通过 → 直接返回"未找到相关信息"，不调用 LLM
    3. prompt_builder.build_context(chunks) 组装 context 字符串
    4. 把 context 渲染进 SYSTEM_PROMPT
    5. llm_client.generate(...)             LangChain LCEL chain 调用 LLM
    6. reflection.reflect(...)              Reflection（当前为占位实现）
    7. 返回 AnswerResult

Reflection 接口预留说明：
    pipeline.py 正常调用 reflection.reflect()，使用其返回的
    ReflectionResult.final_answer 作为最终答案。
    下阶段只需替换 reflection.reflect() 函数体，不需要改动此文件。
"""

from __future__ import annotations

import logging
import time

from chat_service.trace import TraceBuilder
from qa_service import config, llm_client, prompt_builder, reflection, retrieval
from qa_service.models import AnswerResult

logger = logging.getLogger(__name__)

_NOT_FOUND_ANSWER = "根据现有知识库内容，未能找到与该问题相关的信息。"


def answer_question(question: str) -> AnswerResult:
    """
    对用户问题执行单次检索 + 单次生成，返回最终答案。

    Args:
        question: 用户输入的自然语言问题。

    Returns:
        AnswerResult:
            answer           — 最终呈现给用户的文本
            sources          — 检索到的 chunk_id 列表（未找到时为空列表）
            passed_reflection — Reflection 校验结果（未找到时为 None）
    """
    question = (question or "").strip()
    trace = TraceBuilder()
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
    chunks = retrieval.retrieve(question, k=config.TOP_K)
    trace.add_step(
        "retrieval",
        {
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

    # Step 3: 组装 context
    context = prompt_builder.build_context(chunks)
    trace.add_step("context", {"chars": len(context), "chunks": len(chunks)})

    # Step 4: 渲染 system prompt（把 context 填入 SYSTEM_PROMPT 的 {context} 占位符）
    system_prompt = prompt_builder.SYSTEM_PROMPT.format(context=context)

    # Step 5: 调用 LLM
    llm_started = time.perf_counter()
    draft_answer = llm_client.generate(system_prompt, context, question)
    trace.add_step(
        "llm",
        {
            "model": config.LLM_MODEL,
            "max_tokens": config.LLM_MAX_TOKENS,
            "thinking_enabled": config.LLM_ENABLE_THINKING,
            "question_chars": len(question),
            "context_chars": len(context),
            "answer_chars": len(draft_answer),
        },
        duration_ms=(time.perf_counter() - llm_started) * 1000,
    )

    # Step 6: Reflection（当前阶段为占位实现）
    reflection_result = reflection.reflect(draft_answer, context, chunks)

    answer = AnswerResult(
        answer=reflection_result.final_answer,
        sources=[c.chunk_id for c in chunks],
        passed_reflection=reflection_result.passed,
    )
    trace.add_step(
        "reflection",
        {"passed": reflection_result.passed, "notes": reflection_result.notes},
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
    return answer
