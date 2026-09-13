"""
qa_service.reflection — Reflection 接口与占位实现。
qa_service.reflection — Reflection 阶段实现。

当前阶段（最简版）：reflect() 直接判定为通过，不做任何实际校验。
占位实现保证：
  1. pipeline.py 按正常流程调用此函数
  2. 数据类型（ReflectionResult）与下阶段一致
  3. 下阶段只需替换 reflect() 函数体，不需要改动 pipeline.py
对 LLM 生成的初版草稿答案执行独立的 Reflection 评审。
评估维度：
    1. Factual correctness（事实准确性）
    2. Question relevance（问题相关性）
    3. Completeness（完整性）
    4. Evidence usage（证据使用）
    5. Answer quality（回答质量）

下阶段实现方向（不在本次范围内）：
  - 对 draft_answer 逐句检查是否有 retrieved_chunks 文本支撑
  - 返回不通过时给出修正建议或需要剔除的句子
  - 可用独立 LLM 调用或规则方式实现
若校验成功：保留原答案不变，后附 \\n\\nReflection Note:\\n<reflection result>
若校验异常/失败：保留原答案不变，后附 \\n\\nReflection Note:\\nReflection unavailable.
并将完整的执行元数据记录到 Trace 中。
"""

from __future__ import annotations

import logging
from typing import List
import re
import time
from typing import List, Optional

from qa_service import config, llm_client, prompt_builder
from qa_service.models import ReflectionResult, RetrievedChunk

logger = logging.getLogger(__name__)


def parse_decision(raw_output: str) -> Optional[str]:
    """
    从 Reflection LLM 输出中提取 Decision (PASS / REVISE)。
    若未能匹配则返回 None。
    """
    if not raw_output:
        return None
    match = re.search(
        r"(?:\*{2})?Decision(?:\*{2})?:?\s*(?:\*{2})?:?\s*(?:\*{2})?\s*(PASS|REVISE)\b",
        raw_output,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).upper()
    return None



def reflect(
    question: str,
    context: str,
    draft_answer: str,
    context: str,
    retrieved_chunks: List[RetrievedChunk],
    retrieved_chunks: Optional[List[RetrievedChunk]] = None,
) -> ReflectionResult:
    """
    校验 draft_answer 的每个断言是否有 retrieved_chunks 支撑。
    对 draft_answer 执行独立的 Reflection 评审。

    下一阶段实现：用独立 LLM 调用或规则校验 draft_answer 里每句话
    是否有 retrieved_chunks 支撑，返回校验结果（是否通过 + 修正建议/
    需要剔除的部分）。

    当前阶段：占位实现，直接判定为通过，不做任何实际校验，
    只是保证主流程调用了这个函数、数据结构对得上，方便下阶段
    直接替换函数体，不需要改动 pipeline.py 的调用方式。

    Args:
        draft_answer:     LLM 生成的草稿答案。
        context:          组装好的 context 字符串（供下阶段校验用）。
        retrieved_chunks: 检索到的原始 chunk 列表（供下阶段逐句比对用）。
        question: 用户原始问题。
        context: 组装好的检索上下文。
        draft_answer: LLM 生成的初始答案。
        retrieved_chunks: 原始检索到的 chunk 列表（可选，供未来扩展比对用）。

    Returns:
        ReflectionResult(
            passed=True,
            final_answer=draft_answer,
            notes="占位实现，未做真实校验",
        )
        ReflectionResult: 包含 final_answer (原答案 + Reflection Note) 以及详细 Trace 元数据。
    """
    logger.debug(
        "reflect() called (stub): draft_len=%d, chunks=%d",
        len(draft_answer),
        len(retrieved_chunks),
    start_time = time.perf_counter()
    prompt = prompt_builder.build_reflection_prompt(
        question=question,
        context=context,
        answer=draft_answer,
    )
    return ReflectionResult(
        passed=True,
        final_answer=draft_answer,
        notes="占位实现，未做真实校验",
    )
    model_name = config.LLM_MODEL
    model_cfg = llm_client.get_model_config()

    try:
        raw_output = llm_client.generate_reflection(prompt)
        duration_ms = (time.perf_counter() - start_time) * 1000

        if not raw_output or not raw_output.strip():
            logger.warning("Reflection LLM returned empty response")
            reflection_note = "Reflection unavailable."
            final_answer = f"{draft_answer}\n\nReflection Note:\n{reflection_note}"
            return ReflectionResult(
                passed=None,
                final_answer=final_answer,
                notes=reflection_note,
                decision=None,
                raw_output=raw_output or "",
                error="Reflection LLM returned empty output",
                duration_ms=duration_ms,
                prompt=prompt,
                model=model_name,
                model_config=model_cfg,
            )

        decision = parse_decision(raw_output)
        passed = (decision == "PASS") if decision in ("PASS", "REVISE") else None
        reflection_note = raw_output.strip()
        final_answer = f"{draft_answer}\n\nReflection Note:\n{reflection_note}"

        return ReflectionResult(
            passed=passed,
            final_answer=final_answer,
            notes=reflection_note,
            decision=decision,
            raw_output=raw_output,
            error=None,
            duration_ms=duration_ms,
            prompt=prompt,
            model=model_name,
            model_config=model_cfg,
        )
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.exception("Reflection execution failed: %s", error_msg)
        reflection_note = "Reflection unavailable."
        final_answer = f"{draft_answer}\n\nReflection Note:\n{reflection_note}"
        return ReflectionResult(
            passed=None,
            final_answer=final_answer,
            notes=reflection_note,
            decision="ERROR",
            raw_output="",
            error=error_msg,
            duration_ms=duration_ms,
            prompt=prompt,
            model=model_name,
            model_config=model_cfg,
        )

