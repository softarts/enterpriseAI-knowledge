"""Request and response models for the Ask/RAG API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., description="用户的自然语言问题。")


class AskResponse(BaseModel):
    answer: str = Field("", description="LLM 生成的最终答案（含 chunk_id 引用）。")
    sources: List[str] = Field(default_factory=list, description="检索到的 chunk_id 列表。")
    passed_reflection: Optional[bool] = Field(None, description="Reflection 校验是否通过。")
    trace: Dict[str, Any] = Field(default_factory=dict, description="Ask 执行链路追踪信息。")
    error: Optional[str] = Field(None, description="出错时的可读错误信息。")
