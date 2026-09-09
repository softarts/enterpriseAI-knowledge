"""
Ask (RAG) API routes.

Endpoints:
    POST /api/ask  - 单次检索 + 生成的问答接口；返回答案、来源 chunk_id、Reflection 状态。

与 /api/chat 的区别：
    /api/chat  → ChatService → HF LLM 直接对话（无 RAG）
    /api/ask   → services.qa → qa_service.pipeline → 检索 + LangChain LCEL → 带来源的答案
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from chat_service.services.qa.models import AskRequest, AskResponse
from chat_service.services.qa.service import answer_question

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    """
    单次检索 + 生成问答。

    流程：
        question → embedding → ChromaDB Top-K → 置信度判断
        → context 组装 → LangChain LCEL (ChatOpenAI) → Reflection（占位）
        → AskResponse

    错误以 200 响应返回（error 字段非 null），方便前端在 Ask 面板内渲染。
    """
    try:
        result = answer_question(request.question)
        return AskResponse(
            answer=result.answer,
            sources=result.sources,
            passed_reflection=result.passed_reflection,
            trace=result.trace,
            error=None,
        )
    except EnvironmentError as exc:
        # LLM 环境变量未配置（LLM_BASE_URL / LLM_MODEL / LLM_API_KEY）
        msg = str(exc)
        logger.error("Ask env config error: %s", msg)
        return AskResponse(answer="", sources=[], passed_reflection=None, trace={}, error=msg)
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        logger.exception("Ask pipeline error")
        return AskResponse(answer="", sources=[], passed_reflection=None, trace={}, error=f"问答服务出错：{msg}")
