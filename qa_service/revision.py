"""
qa_service.revision — Revision 阶段实现。

当 Reflection 返回 REVISE 时，调用 Revision 步骤对草稿回答进行针对性修订。
修订要求：
    1. 严格依据检索到的 <context>，不得将评审意见作为事实证据引用；
    2. 删除不必要/超范围的内容；
    3. 补充检索上下文中包含的关键信息；
    4. 纠正或删除无依据的断言；
    5. 保持引用格式规范与段落流畅；
    6. 若 Revision 发生异常或返回为空，安全回退到初始草稿答案。
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from qa_service import config, llm_client, prompt_builder
from qa_service.models import ReflectionResult, RevisionResult

logger = logging.getLogger(__name__)


def revise(
    question: str,
    context: str,
    draft_answer: str,
    reflection_result: ReflectionResult,
) -> RevisionResult:
    """
    对草稿回答执行针对性修订。

    Args:
        question: 用户原始问题。
        context: 组装好的检索上下文（唯一事实依据）。
        draft_answer: LLM 生成的初版草稿答案。
        reflection_result: Reflection 评审阶段的完整结果。

    Returns:
        RevisionResult: 包含修订后文本及链路追踪元数据。
    """
    start_time = time.perf_counter()
    feedback_text = (
        reflection_result.raw_output.strip()
        if reflection_result.raw_output
        else reflection_result.notes
    )

    prompt = prompt_builder.build_revision_prompt(
        question=question,
        context=context,
        draft_answer=draft_answer,
        reflection_feedback=feedback_text,
    )

    input_data = {
        "question": question,
        "context_chars": len(context),
        "draft_answer": draft_answer,
        "reflection_feedback": feedback_text,
    }

    model_name = config.LLM_MODEL

    try:
        revised_answer = llm_client.generate_revision(prompt)
        duration_ms = (time.perf_counter() - start_time) * 1000

        if not revised_answer or not revised_answer.strip():
            logger.warning("Revision LLM returned empty response")
            return RevisionResult(
                executed=True,
                status="error",
                revised_answer="",
                prompt=prompt,
                input=input_data,
                output=revised_answer or "",
                error="Revision LLM returned empty output",
                duration_ms=duration_ms,
                model=model_name,
            )

        return RevisionResult(
            executed=True,
            status="success",
            revised_answer=revised_answer.strip(),
            prompt=prompt,
            input=input_data,
            output=revised_answer,
            error=None,
            duration_ms=duration_ms,
            model=model_name,
        )
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.exception("Revision execution failed: %s", error_msg)
        return RevisionResult(
            executed=True,
            status="error",
            revised_answer="",
            prompt=prompt,
            input=input_data,
            output="",
            error=error_msg,
            duration_ms=duration_ms,
            model=model_name,
        )
