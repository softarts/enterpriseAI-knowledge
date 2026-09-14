"""
qa_service.reflection — Reflection 阶段实现。

对 LLM 生成的初版草稿答案执行独立的 Reflection 评审。
评估维度：
    1. Factual correctness（事实准确性）
    2. Direct relevance（直接相关性）
    3. Scope control（范围控制）
    4. Completeness（完整性）
    5. Evidence support（证据支持）

输出结构化判定：
    - PASS: 草稿准确、切题、范围适度，直接作为最终答案；
    - REVISE: 存在范围超标、关键缺失或不实断言，触发 Revision 环节进行修订；
    - 失败/异常: 安全降级，保留草稿答案，错误记录到 Trace 中。
"""

from __future__ import annotations

import logging
import re
import time
from typing import List, Optional

from qa_service import config, llm_client, prompt_builder
from qa_service.models import ParsedReflection, ReflectionResult, RetrievedChunk

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


def parse_reflection_output(raw_output: str) -> ParsedReflection:
    """
    将 Reflection LLM 的文本输出解析为结构化的 ParsedReflection 对象。
    """
    if not raw_output or not raw_output.strip():
        return ParsedReflection(decision=None)

    decision = parse_decision(raw_output)

    headers = [
        ("reasons", r"Reasons:?"),
        ("unnecessary_content", r"Unnecessary or out-of-scope content:?"),
        ("missing_information", r"Missing important information:?"),
        ("unsupported_claims", r"Unsupported claims:?"),
    ]

    spans = []
    for key, pattern in headers:
        match = re.search(r"(?:^|\n)\s*(?:\*{0,2})" + pattern, raw_output, re.IGNORECASE)
        if match:
            spans.append((match.start(), match.end(), key))

    spans.sort(key=lambda x: x[0])
    section_texts = {}
    for i, (start, end, key) in enumerate(spans):
        next_start = spans[i + 1][0] if i + 1 < len(spans) else len(raw_output)
        section_texts[key] = raw_output[end:next_start].strip()

    def extract_bullets(text: str) -> List[str]:
        if not text:
            return []
        items: List[str] = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            item = re.sub(r"^[-*•\d\.]+\s*", "", line).strip().strip("\"'")
            if item and item.lower() not in {"none", "none.", "无", "n/a", "na"}:
                items.append(item)
        return items

    return ParsedReflection(
        decision=decision,
        reasons=extract_bullets(section_texts.get("reasons", "")),
        unnecessary_content=extract_bullets(section_texts.get("unnecessary_content", "")),
        missing_information=extract_bullets(section_texts.get("missing_information", "")),
        unsupported_claims=extract_bullets(section_texts.get("unsupported_claims", "")),
    )


def reflect(
    question: str,
    context: str,
    draft_answer: str,
    retrieved_chunks: Optional[List[RetrievedChunk]] = None,
) -> ReflectionResult:
    """
    对 draft_answer 执行独立的 Reflection 评审。

    Args:
        question: 用户原始问题。
        context: 组装好的检索上下文。
        draft_answer: LLM 生成的初始答案。
        retrieved_chunks: 原始检索到的 chunk 列表（可选）。

    Returns:
        ReflectionResult: 包含结构化决策、解析结果及详细 Trace 元数据。
    """
    start_time = time.perf_counter()
    prompt = prompt_builder.build_reflection_prompt(
        question=question,
        context=context,
        answer=draft_answer,
    )
    model_name = config.get_reflection_model()
    model_source = config.get_reflection_model_source()
    model_cfg = llm_client.get_reflection_model_config()

    try:
        raw_output = llm_client.generate_reflection(prompt)
        duration_ms = (time.perf_counter() - start_time) * 1000

        if not raw_output or not raw_output.strip():
            logger.warning("Reflection LLM returned empty response")
            return ReflectionResult(
                enabled=True,
                status="error",
                passed=None,
                final_answer=draft_answer,
                notes="Reflection returned empty output",
                decision=None,
                raw_output=raw_output or "",
                parsed_result=ParsedReflection(decision=None),
                error="Reflection LLM returned empty output",
                duration_ms=duration_ms,
                prompt=prompt,
                model=model_name,
                model_source=model_source,
                model_config=model_cfg,
            )

        parsed = parse_reflection_output(raw_output)
        if parsed.decision not in ("PASS", "REVISE"):
            logger.warning("Reflection LLM output lacked valid PASS/REVISE decision")
            return ReflectionResult(
                enabled=True,
                status="error",
                passed=None,
                final_answer=draft_answer,
                notes="Invalid or missing reflection decision",
                decision=None,
                raw_output=raw_output,
                parsed_result=parsed,
                error="Reflection output lacked valid PASS or REVISE decision",
                duration_ms=duration_ms,
                prompt=prompt,
                model=model_name,
                model_source=model_source,
                model_config=model_cfg,
            )

        passed = (parsed.decision == "PASS")
        return ReflectionResult(
            enabled=True,
            status="success",
            passed=passed,
            final_answer=draft_answer,
            notes=raw_output.strip(),
            decision=parsed.decision,
            raw_output=raw_output,
            parsed_result=parsed,
            error=None,
            duration_ms=duration_ms,
            prompt=prompt,
            model=model_name,
            model_source=model_source,
            model_config=model_cfg,
        )
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.exception("Reflection execution failed: %s", error_msg)
        return ReflectionResult(
            enabled=True,
            status="error",
            passed=None,
            final_answer=draft_answer,
            notes=error_msg,
            decision=None,
            raw_output="",
            parsed_result=ParsedReflection(decision=None),
            error=error_msg,
            duration_ms=duration_ms,
            prompt=prompt,
            model=model_name,
            model_source=model_source,
            model_config=model_cfg,
        )
