"""
qa_service 内部数据类。

故意不复用 embedding_service.models.EmbeddedChunk，避免 qa_service
与 embedding_service 形成强耦合——未来换存储方案时只改 retrieval.py。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RetrievedChunk:
    """单条检索结果，由 retrieval.py 从 VectorSearchResult 转换而来。"""

    chunk_id: str
    document_id: str
    title: str
    heading: Optional[str]
    source_path: str
    text: str
    distance: float   # cosine distance；越小越相似（范围 [0, 2]）
    rank: int         # 检索排名（1-indexed）


@dataclass
class ReflectionResult:
    """
    Reflection 阶段的校验结果。

    当前阶段为占位实现（passed=True，final_answer == draft_answer）。
    下阶段替换 reflection.reflect() 函数体时，此数据类不需要改动。
    """

    passed: bool
    final_answer: str
    notes: str


@dataclass
class AnswerResult:
    """pipeline.answer_question() 返回给调用方的最终结果。"""

    answer: str
    sources: List[str] = field(default_factory=list)  # chunk_id 列表
    passed_reflection: Optional[bool] = None
