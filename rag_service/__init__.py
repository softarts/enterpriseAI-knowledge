"""rag_service — LangGraph 原生编排的 RAG 问答服务（qa_service 的替代实现）。

编排：START → retrieve → generate ↔ tools(search_memory) → critic ↔ revise
      → finalize → update_memory → END

记忆：编译时挂载 Checkpointer（短期）+ Store（长期），调用时传 thread_id；
不使用已废弃的 langchain_memory 模块，也没有手写 memory_runtime 逻辑。
"""

from rag_service.models import AnswerResult
from rag_service.runtime import RagRuntime, answer_question, get_default_runtime

__all__ = ["AnswerResult", "RagRuntime", "answer_question", "get_default_runtime"]
