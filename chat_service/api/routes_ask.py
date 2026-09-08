"""
Ask (RAG) API routes.

Endpoints:
    POST /api/ask  - 单次检索 + 生成的问答接口；返回答案、来源 chunk_id、Reflection 状态。

与 /api/chat 的区别：
    /api/chat  → ChatService → HF LLM 直接对话（无 RAG）
    /api/ask   → qa_service.pipeline → 检索 + LangChain LCEL → 带来源的答案
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from qa_service.pipeline import answer_question

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    """单次 Ask（RAG）请求。"""

    question: str = Field(..., description="用户的自然语言问题。")


class AskResponse(BaseModel):
    """Ask（RAG）响应，包含答案、来源引用和 Reflection 状态。"""

    answer: str = Field("", description="LLM 生成的最终答案（含 chunk_id 引用）。")
    sources: List[str] = Field(
        default_factory=list,
        description="检索到的 chunk_id 列表；置信度不足时为空列表。",
    )
    passed_reflection: Optional[bool] = Field(
        None,
        description="Reflection 校验是否通过；置信度不足时为 null（当前为占位实现，始终为 true）。",
    )
    error: Optional[str] = Field(None, description="出错时的可读错误信息。")


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
            error=None,
        )
    except EnvironmentError as exc:
        # LLM 环境变量未配置（LLM_BASE_URL / LLM_MODEL / LLM_API_KEY）
        msg = str(exc)
        logger.error("Ask env config error: %s", msg)
        return AskResponse(answer="", sources=[], passed_reflection=None, error=msg)
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        logger.exception("Ask pipeline error")
        return AskResponse(answer="", sources=[], passed_reflection=None, error=f"问答服务出错：{msg}")
