"""rag_service.state — RAG 图的共享状态定义。

messages 由 add_messages reducer 管理，随 Checkpointer 按 thread_id 持久化，
即短期对话历史；其余字段是单次问答的工作流产物。

trace_steps 使用按 turn 过滤的 reducer：每个 turn 由 retrieve 节点分配新的
turn_id，旧 turn 的步骤在下一轮被自动丢弃，避免 checkpoint 中无限累积。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict
from typing_extensions import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def _merge_trace_steps(
    existing: Optional[List[Dict[str, Any]]],
    new: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Append trace steps within one turn; drop steps from previous turns.

    Each step dict carries a private ``_turn`` key. When incoming steps belong
    to a new turn, all steps from older turns are discarded so the checkpoint
    only ever holds the current turn's trace.
    """
    if not new:
        return list(existing or [])
    turn = new[0].get("_turn")
    kept = [step for step in (existing or []) if step.get("_turn") == turn]
    return kept + [dict(step) for step in new]


def trace_step(
    turn_id: str,
    name: str,
    detail: Dict[str, Any],
    status: str = "ok",
    duration_ms: Optional[float] = None,
) -> Dict[str, Any]:
    """Build one trace step entry in the shape TraceBuilder.add_step() expects."""
    return {
        "name": name,
        "status": status,
        "detail": detail,
        "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        "_turn": turn_id,
    }


class RagState(TypedDict, total=False):
    """State schema for the RAG graph.

    - messages: short-term conversation history, owned by the Checkpointer.
      search_memory 的 ToolMessage 也在这个列表里（由 ToolNode 产生）。
    - question / enterprise_context / chunks: retrieve 节点的产物。
    - current_answer: 当前候选答案；generate 写入草稿，revise 成功后覆盖。
    - reflection: 最近一次 critic 的评审信息（decision/passed/raw_output 等）。
    - revision_count / revision_status: critic↔revise 循环控制。
    """

    messages: Annotated[List[BaseMessage], add_messages]
    turn_id: str
    question: str
    enterprise_context: str
    chunks: List[Dict[str, Any]]
    retrieval_ok: bool
    draft_answer: str
    current_answer: str
    reflection: Dict[str, Any]
    is_satisfactory: bool
    passed_reflection: Optional[bool]
    revision_count: int
    revision_status: Optional[str]  # None | "success" | "error"
    final_answer: str
    sources: List[str]
    trace_steps: Annotated[List[Dict[str, Any]], _merge_trace_steps]
