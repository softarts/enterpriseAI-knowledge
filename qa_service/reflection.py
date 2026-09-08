"""
qa_service.reflection — Reflection 接口与占位实现。

当前阶段（最简版）：reflect() 直接判定为通过，不做任何实际校验。
占位实现保证：
  1. pipeline.py 按正常流程调用此函数
  2. 数据类型（ReflectionResult）与下阶段一致
  3. 下阶段只需替换 reflect() 函数体，不需要改动 pipeline.py

下阶段实现方向（不在本次范围内）：
  - 对 draft_answer 逐句检查是否有 retrieved_chunks 文本支撑
  - 返回不通过时给出修正建议或需要剔除的句子
  - 可用独立 LLM 调用或规则方式实现
"""

from __future__ import annotations

import logging
from typing import List

from qa_service.models import ReflectionResult, RetrievedChunk

logger = logging.getLogger(__name__)


def reflect(
    draft_answer: str,
    context: str,
    retrieved_chunks: List[RetrievedChunk],
) -> ReflectionResult:
    """
    校验 draft_answer 的每个断言是否有 retrieved_chunks 支撑。

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

    Returns:
        ReflectionResult(
            passed=True,
            final_answer=draft_answer,
            notes="占位实现，未做真实校验",
        )
    """
    logger.debug(
        "reflect() called (stub): draft_len=%d, chunks=%d",
        len(draft_answer),
        len(retrieved_chunks),
    )
    return ReflectionResult(
        passed=True,
        final_answer=draft_answer,
        notes="占位实现，未做真实校验",
    )
