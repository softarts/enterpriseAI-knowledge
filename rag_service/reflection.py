"""rag_service.reflection — critic 节点（由 qa_service.reflection 改造而来）。

原 qa_service.reflection.reflect() 是被 pipeline 顺序调用的纯函数；
这里保留其 prompt 构建与输出解析逻辑不变，外层包装为 LangGraph 节点：

    critic_node(state) -> {"is_satisfactory", "reflection", "passed_reflection", "trace_steps"}

评估维度与判定语义不变：
    - PASS:   is_satisfactory=True  → 条件边路由到 finalize
    - REVISE: is_satisfactory=False → 条件边在 revision_count 未达上限时路由到 revise
    - 失败/异常: 安全降级，is_satisfactory=True（保留当前答案），错误记录到 trace
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional

from rag_service import config, llm_client, prompt_builder
from rag_service.models import ParsedReflection, ReflectionResult
from rag_service.state import RagState, trace_step

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


def reflect(question: str, context: str, draft_answer: str) -> ReflectionResult:
    """
    对 draft_answer 执行一次 Reflection 评审（critic 的单次执行体）。

    语义与 qa_service.reflection.reflect() 一致：成功时 decision 为
    PASS/REVISE，任何异常安全降级为 status="error"、保留当前答案。
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

        passed = parsed.decision == "PASS"
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


def critic_node(state: RagState) -> Dict[str, Any]:
    """Critic 节点：评审 state["current_answer"]，写入 is_satisfactory。

    Reflection 被配置关闭时直接放行（is_satisfactory=True），trace 中记录
    skipped 步骤，保持与手写 pipeline 相同的 trace 契约。
    """
    question = state["question"]
    context = state.get("enterprise_context", "")
    current_answer = state.get("current_answer", "")
    turn_id = state.get("turn_id", "")
    round_index = state.get("revision_count", 0)

    if not config.is_reflection_enabled():
        logger.info("rag.critic.skip thread turn=%s reason=reflection_disabled", turn_id)
        return {
            "is_satisfactory": True,
            "passed_reflection": None,
            "reflection": {"status": "skipped", "decision": None},
            "trace_steps": [
                trace_step(
                    turn_id,
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
                        "round": round_index,
                    },
                    status="skipped",
                )
            ],
        }

    result = reflect(
        question=question,
        context=context,
        draft_answer=current_answer,
    )
    parsed = result.parsed_result
    # 评审失败时安全降级：视为"可接受"，路由到 finalize 保留当前答案。
    is_satisfactory = result.status != "success" or result.decision == "PASS"

    logger.info(
        "rag.critic.completed turn=%s round=%d status=%s decision=%s",
        turn_id,
        round_index,
        result.status,
        result.decision,
    )

    return {
        "is_satisfactory": is_satisfactory,
        "passed_reflection": result.passed,
        "reflection": {
            "status": result.status,
            "decision": result.decision,
            "raw_output": result.raw_output,
            "notes": result.notes,
            "error": result.error,
        },
        "trace_steps": [
            trace_step(
                turn_id,
                "reflection",
                {
                    "enabled": True,
                    "status": result.status,
                    "model": result.model,
                    "model_source": result.model_source,
                    "prompt": result.prompt,
                    "input": {
                        "question": question,
                        "context": context,
                        "answer": current_answer,
                    },
                    "output": result.raw_output,
                    "parsed_result": parsed.to_dict() if parsed else None,
                    "decision": result.decision,
                    "reasons": parsed.reasons if parsed else [],
                    "unnecessary_content": parsed.unnecessary_content if parsed else [],
                    "missing_information": parsed.missing_information if parsed else [],
                    "unsupported_claims": parsed.unsupported_claims if parsed else [],
                    "error": result.error,
                    "round": round_index,
                },
                status="ok" if result.status == "success" else "error",
                duration_ms=result.duration_ms,
            )
        ],
    }


def route_after_critic(state: RagState) -> str:
    """条件边：PASS / 评审失败 / 达到 MAX_REVISION 上限 → finalize；否则 → revise。"""
    if state.get("is_satisfactory"):
        return "finalize"
    if state.get("revision_count", 0) >= config.MAX_REVISION:
        logger.info(
            "rag.critic.max_revision_reached count=%d limit=%d",
            state.get("revision_count", 0),
            config.MAX_REVISION,
        )
        return "finalize"
    return "revise"
