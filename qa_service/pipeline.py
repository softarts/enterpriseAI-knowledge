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
    if not question:
        logger.warning("answer_question() called with empty question")
        return AnswerResult(answer=_NOT_FOUND_ANSWER, sources=[], passed_reflection=None)

    # Step 1: 向量检索
    chunks = retrieval.retrieve(question, k=config.TOP_K)

    # Step 2: 置信度判断
    if not retrieval.is_confident(chunks, threshold=config.CONFIDENCE_THRESHOLD):
        logger.info("Confidence check failed; returning not-found answer")
        return AnswerResult(answer=_NOT_FOUND_ANSWER, sources=[], passed_reflection=None)

    # Step 3: 组装 context
    context = prompt_builder.build_context(chunks)

    # Step 4: 渲染 system prompt（把 context 填入 SYSTEM_PROMPT 的 {context} 占位符）
    system_prompt = prompt_builder.SYSTEM_PROMPT.format(context=context)

    # Step 5: 调用 LLM
    draft_answer = llm_client.generate(system_prompt, context, question)

    # Step 6: Reflection（当前阶段为占位实现）
    reflection_result = reflection.reflect(draft_answer, context, chunks)

    return AnswerResult(
        answer=reflection_result.final_answer,
        sources=[c.chunk_id for c in chunks],
        passed_reflection=reflection_result.passed,
    )
