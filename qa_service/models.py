"""
qa_service 内部数据类。

故意不复用 embedding_service.models.EmbeddedChunk，避免 qa_service
与 embedding_service 形成强耦合——未来换存储方案时只改 retrieval.py。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
class ParsedReflection:
    """结构化解析后的 Reflection 输出。"""

    decision: Optional[str] = None  # "PASS" | "REVISE" | None
    reasons: List[str] = field(default_factory=list)
    unnecessary_content: List[str] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)
    unsupported_claims: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": self.reasons,
            "unnecessary_content": self.unnecessary_content,
            "missing_information": self.missing_information,
            "unsupported_claims": self.unsupported_claims,
        }


@dataclass
class ReflectionResult:
    """Reflection 阶段的执行结果。"""

    enabled: bool = True
    status: str = "success"  # "success" | "error" | "skipped"
    passed: Optional[bool] = None
    final_answer: str = ""
    notes: str = ""
    decision: Optional[str] = None
    raw_output: str = ""
    parsed_result: Optional[ParsedReflection] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    prompt: str = ""
    model: str = ""
    model_source: str = ""  # "REFLECTION_MODEL" | "LLM_MODEL fallback"
    model_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RevisionResult:
    """Revision 阶段的执行结果。"""

    executed: bool = False
    status: str = "skipped"  # "success" | "error" | "skipped"
    revised_answer: str = ""
    prompt: str = ""
    input: Dict[str, Any] = field(default_factory=dict)
    output: str = ""
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    model: str = ""



@dataclass
class AnswerResult:
    """pipeline.answer_question() 返回给调用方的最终结果。"""

    answer: str
    sources: List[str] = field(default_factory=list)  # chunk_id 列表
    passed_reflection: Optional[bool] = None
    trace: Dict[str, Any] = field(default_factory=dict)
