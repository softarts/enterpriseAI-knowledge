"""rag_service.revision — revise 节点（由 qa_service.revision 改造而来）。

原 qa_service.revision.revise() 是被 pipeline 顺序调用的纯函数；
这里保留其 prompt 构建与 LLM 调用逻辑不变，外层包装为 LangGraph 节点：

    revise_node(state) -> {"current_answer", "revision_count", "revision_status", "trace_steps"}

修订语义不变：
    1. 严格依据检索到的 <context>，不把评审意见当作事实证据；
    2. 成功：覆盖 current_answer，revision_count + 1，条件边回到 critic 复审；
    3. 失败/异常/空输出：安全回退，current_answer 保持不动（draft 或上一版
       成功修订），revision_status="error"，条件边直接路由到 finalize。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from rag_service import config, llm_client, prompt_builder
from rag_service.models import RevisionResult
from rag_service.state import RagState, trace_step

logger = logging.getLogger(__name__)


def revise(
    question: str,
    context: str,
    draft_answer: str,
    reflection_feedback: str,
) -> RevisionResult:
    """
    对当前答案执行一次针对性修订（revise 节点的单次执行体）。

    语义与 qa_service.revision.revise() 一致：任何异常或空输出都返回
    status="error"，由节点层回退到修订前答案。
    """
    start_time = time.perf_counter()
    prompt = prompt_builder.build_revision_prompt(
        question=question,
        context=context,
        draft_answer=draft_answer,
        reflection_feedback=reflection_feedback,
    )

    input_data = {
        "question": question,
        "context_chars": len(context),
        "draft_answer": draft_answer,
        "reflection_feedback": reflection_feedback,
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


def revise_node(state: RagState) -> Dict[str, Any]:
    """Revise 节点：根据最近一次 critic 反馈修订 current_answer。

    成功时 revision_count + 1 并回到 critic 复审；失败时保留修订前答案，
    由 route_after_revise 路由到 finalize。
    """
    question = state["question"]
    context = state.get("enterprise_context", "")
    current_answer = state.get("current_answer", "")
    turn_id = state.get("turn_id", "")
    round_index = state.get("revision_count", 0)
    reflection = state.get("reflection", {})
    feedback_text = (reflection.get("raw_output") or reflection.get("notes") or "").strip()

    result = revise(
        question=question,
        context=context,
        draft_answer=current_answer,
        reflection_feedback=feedback_text,
    )

    step = trace_step(
        turn_id,
        "revision",
        {
            "executed": True,
            "status": result.status,
            "model": result.model,
            "prompt": result.prompt,
            "input": result.input,
            "output": result.output,
            "error": result.error,
            "round": round_index,
        },
        status="ok" if result.status == "success" else "error",
        duration_ms=result.duration_ms,
    )

    if result.status == "success" and result.revised_answer:
        logger.info(
            "rag.revise.completed turn=%s round=%d answer_chars=%d",
            turn_id,
            round_index,
            len(result.revised_answer),
        )
        return {
            "current_answer": result.revised_answer,
            "revision_count": round_index + 1,
            "revision_status": "success",
            "trace_steps": [step],
        }

    logger.warning(
        "rag.revise.failed turn=%s round=%d error=%s; falling back to previous answer",
        turn_id,
        round_index,
        result.error,
    )
    # 回退：不修改 current_answer，条件边将路由到 finalize。
    return {
        "revision_status": "error",
        "trace_steps": [step],
    }


def route_after_revise(state: RagState) -> str:
    """条件边：修订成功 → critic 复审；修订失败（已回退）→ finalize。"""
    if state.get("revision_status") == "success":
        return "critic"
    return "finalize"
