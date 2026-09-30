"""rag_service.graph — RAG 编排的 LangGraph 原生实现。

图结构（节点 + 边）：

    START → retrieve
    retrieve ──(confidence 未过)──────────────→ finalize
    retrieve ──(confidence 通过)→ generate
    generate ──(AIMessage 带 tool_calls)→ tools → generate   # search_memory 工具循环
    generate ──(最终答复)→ critic
    critic ──(PASS / 评审失败 / 达到 MAX_REVISION)→ finalize
    critic ──(REVISE 且未达上限)→ revise
    revise ──(修订成功)→ critic                              # 复审修订稿
    revise ──(修订失败，已回退)→ finalize
    finalize → update_memory → END

记忆层：
    编译时挂载 Checkpointer（短期，按 thread_id 恢复 messages）与
    Store（长期，search_memory 工具读取、update_memory 节点写入），
    对话历史完全由框架管理，没有手写 prepare_context / memory_runtime。

防死循环：
    critic↔revise 由 state.revision_count 与 config.MAX_REVISION 限制；
    generate↔tools 与整条图再由 runtime 传入的 recursion_limit 兜底。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore

from langchain_agent.app import config as agent_config
from langchain_agent.app.graph import create_update_memory_node
from langchain_agent.app.long_memory import (
    create_memory_store,
    create_search_memory_tool,
)

from rag_service import config, llm_client, prompt_builder, retrieval
from rag_service.reflection import critic_node, route_after_critic
from rag_service.revision import revise_node, route_after_revise
from rag_service.state import RagState, trace_step

logger = logging.getLogger(__name__)

# generate 节点的系统提示补充：说明唯一可用的记忆工具及其边界。
_MEMORY_TOOL_HINT = (
    "\n\n当问题依赖用户的稳定偏好、长期背景或用户此前要求记住的事实时，"
    "可调用 search_memory 工具查询长期记忆；<context> 已能回答的问题不要调用。"
)


# ---------------------------------------------------------------------------
# retrieve 节点
# ---------------------------------------------------------------------------


def retrieve_node(state: RagState) -> Dict[str, Any]:
    """向量检索 + 置信度判断 + 企业 context 组装。

    confidence 未过时 retrieval_ok=False，条件边直接路由到 finalize，
    不调用 LLM（与手写 pipeline 行为一致）。
    """
    question = state["question"]
    turn_id = uuid.uuid4().hex
    started = time.perf_counter()

    chunks = retrieval.retrieve(question, k=config.TOP_K)
    retrieval_ms = (time.perf_counter() - started) * 1000
    confident = retrieval.is_confident(chunks, threshold=config.CONFIDENCE_THRESHOLD)

    chunk_dicts: List[Dict[str, Any]] = [
        {
            "rank": c.rank,
            "chunk_id": c.chunk_id,
            "document_id": c.document_id,
            "title": c.title,
            "source_path": c.source_path,
            "heading": c.heading,
            "distance": c.distance,
            "text": c.text,
        }
        for c in chunks
    ]
    steps = [
        trace_step(
            turn_id,
            "retrieval",
            {
                "query": question,
                "top_k": config.TOP_K,
                "count": len(chunks),
                "top_distance": chunks[0].distance if chunks else None,
                "chunks": [
                    {k: c[k] for k in ("rank", "chunk_id", "document_id", "source_path", "heading", "distance")}
                    for c in chunk_dicts
                ],
            },
            duration_ms=retrieval_ms,
        ),
        trace_step(
            turn_id,
            "confidence",
            {
                "passed": confident,
                "threshold": config.CONFIDENCE_THRESHOLD,
                "top_distance": chunks[0].distance if chunks else None,
            },
        ),
    ]

    updates: Dict[str, Any] = {
        "turn_id": turn_id,
        "chunks": chunk_dicts if confident else [],
        "retrieval_ok": confident,
        "revision_count": 0,
        "revision_status": None,
        "trace_steps": steps,
    }
    if not confident:
        logger.info("rag.retrieve.not_confident turn=%s", turn_id)
        return updates

    enterprise_context = prompt_builder.build_context(chunks)
    updates["enterprise_context"] = enterprise_context
    updates["trace_steps"] = steps + [
        trace_step(
            turn_id,
            "context",
            {
                "chars": len(enterprise_context),
                "enterprise_chars": len(enterprise_context),
                "chunks": len(chunks),
                "thread_history_managed_by": "langgraph_checkpointer",
            },
        )
    ]
    logger.info(
        "rag.retrieve.completed turn=%s chunks=%d context_chars=%d",
        turn_id,
        len(chunks),
        len(enterprise_context),
    )
    return updates


def route_after_retrieve(state: RagState) -> str:
    """条件边：检索置信度通过 → generate；否则 → finalize（返回"未找到"）。"""
    if state.get("retrieval_ok"):
        return "generate"
    return "finalize"


# ---------------------------------------------------------------------------
# generate 节点（挂 search_memory 工具的 agent 节点）
# ---------------------------------------------------------------------------


def create_generate_node(llm: BaseChatModel, tools: List[BaseTool]):
    """创建 RAG 生成节点。

    System prompt 每次运行时用 state["enterprise_context"] 现渲染，只 prepend
    不写入 messages；对话历史由 Checkpointer 提供。bind_tools 只挂
    search_memory，是否调用由模型在工具循环内决定。
    """
    llm_with_tools = llm.bind_tools(list(tools)) if tools else llm
    # LangGraph 按参数名注入第二个位置参数 config，节点内以此别名引用模块配置。
    module_config = config

    def generate(state: RagState, config: RunnableConfig) -> Dict[str, Any]:
        turn_id = state.get("turn_id", "")
        question = state["question"]
        enterprise_context = state.get("enterprise_context", "")
        system_content = (
            prompt_builder.SYSTEM_PROMPT.format(context=enterprise_context)
            + _MEMORY_TOOL_HINT
        )
        messages = list(state["messages"])
        outbound: List[BaseMessage] = [SystemMessage(content=system_content)] + messages
        configurable = config.get("configurable", {})
        logger.info(
            "rag.generate.invoke turn=%s thread_id=%s message_count=%d",
            turn_id,
            configurable.get("thread_id"),
            len(messages),
        )

        started = time.perf_counter()
        response = llm_with_tools.invoke(outbound, config=config)
        duration_ms = (time.perf_counter() - started) * 1000

        updates: Dict[str, Any] = {"messages": [response]}
        tool_calls = getattr(response, "tool_calls", None) or []
        logger.info(
            "rag.generate.completed turn=%s tool_calls=%d",
            turn_id,
            len(tool_calls),
        )
        if not tool_calls:
            content = response.content
            if not isinstance(content, str):
                content = "".join(
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict)
                )
            updates["draft_answer"] = content
            updates["current_answer"] = content
            updates["trace_steps"] = [
                trace_step(
                    turn_id,
                    "llm",
                    {
                        "model": module_config.LLM_MODEL,
                        "max_tokens": module_config.LLM_MAX_TOKENS,
                        "thinking_enabled": module_config.LLM_ENABLE_THINKING,
                        "question_chars": len(question),
                        "context_chars": len(enterprise_context),
                        "raw_output": content,
                        "answer_chars": len(content),
                    },
                    duration_ms=duration_ms,
                )
            ]
        return updates

    return generate


def route_after_generate(state: RagState) -> str:
    """条件边：最后一条 AIMessage 带 tool_calls → tools；否则 → critic。"""
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "critic"


# ---------------------------------------------------------------------------
# finalize 节点
# ---------------------------------------------------------------------------


def finalize_node(state: RagState) -> Dict[str, Any]:
    """收敛最终答案：写 final_answer/sources，并把最终答复并入 messages。

    - 检索未通过：统一"未找到"答复，不记录 reflection/revision 步骤
      （与手写 pipeline 的提前返回一致）。
    - revise 从未执行：补一条 skipped 的 revision trace 步骤。
    - 最终答复与最后一条 AI 消息不同（发生过修订）时，追加一条 AIMessage，
      使 checkpoint 中的对话历史保存的是最终答案。
    """
    turn_id = state.get("turn_id", "")
    messages = list(state.get("messages", []))
    steps: List[Dict[str, Any]] = []

    if not state.get("retrieval_ok"):
        final_answer = config.NOT_FOUND_ANSWER
        sources: List[str] = []
        passed_reflection: Optional[bool] = None
        output_source = "not_found"
        draft_answer = ""
        revised_answer: Optional[str] = None
    else:
        draft_answer = state.get("draft_answer", "")
        final_answer = state.get("current_answer", "") or draft_answer
        sources = [c["chunk_id"] for c in state.get("chunks", [])]
        passed_reflection = state.get("passed_reflection")
        revised_applied = bool(final_answer) and final_answer != draft_answer
        output_source = "revision" if revised_applied else "generation"
        revised_answer = final_answer if revised_applied else None

        if state.get("revision_status") is None:
            # revise 未执行（PASS / 评审失败 / Reflection 关闭）：补 skipped 步骤。
            steps.append(
                trace_step(
                    turn_id,
                    "revision",
                    {
                        "executed": False,
                        "status": "skipped",
                        "model": None,
                        "prompt": None,
                        "input": None,
                        "output": None,
                        "error": None,
                    },
                    status="skipped",
                )
            )
        steps.append(
            trace_step(
                turn_id,
                "final_output",
                {
                    "answer": final_answer,
                    "source": output_source,
                    "status": "success",
                    "draft_answer": draft_answer,
                    "revised_answer": revised_answer,
                },
            )
        )

    updates: Dict[str, Any] = {
        "final_answer": final_answer,
        "sources": sources,
        "passed_reflection": passed_reflection,
        "trace_steps": steps,
    }

    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage) or last.content != final_answer:
        updates["messages"] = [AIMessage(content=final_answer)]

    logger.info(
        "rag.finalize.completed turn=%s source=%s answer_chars=%d",
        turn_id,
        output_source,
        len(final_answer),
    )
    return updates


# ---------------------------------------------------------------------------
# 图装配
# ---------------------------------------------------------------------------


def build_rag_graph(
    llm: Optional[BaseChatModel] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    store: Optional[BaseStore] = None,
    tools: Optional[List[BaseTool]] = None,
) -> CompiledStateGraph:
    """编译 RAG 图，挂载 Checkpointer（短期记忆）与 Store（长期记忆）。

    Args:
        llm:         生成用聊天模型；默认取 rag_service.llm_client.get_llm()。
        checkpointer: 短期记忆后端；默认进程内 MemorySaver。
        store:       长期记忆后端；默认由 langchain_agent 的
                     create_memory_store() 创建（带 embedding 索引）。
        tools:       generate 节点可用的工具；默认仅 search_memory。

    Returns:
        编译后的图；调用时传 config={"configurable": {"thread_id": ...}}。
    """
    active_llm = llm or llm_client.get_llm()
    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()
    active_store = store if store is not None else create_memory_store()
    active_tools: List[BaseTool] = (
        list(tools)
        if tools is not None
        else [create_search_memory_tool(default_top_k=agent_config.MEMORY_TOP_K)]
    )

    workflow = StateGraph(RagState)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("generate", create_generate_node(active_llm, active_tools))
    workflow.add_node("tools", ToolNode(active_tools))
    workflow.add_node("critic", critic_node)
    workflow.add_node("revise", revise_node)
    workflow.add_node("finalize", finalize_node)
    workflow.add_node("update_memory", create_update_memory_node(active_llm))

    workflow.add_edge(START, "retrieve")
    workflow.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"generate": "generate", "finalize": "finalize"},
    )
    workflow.add_conditional_edges(
        "generate",
        route_after_generate,
        {"tools": "tools", "critic": "critic"},
    )
    workflow.add_edge("tools", "generate")
    workflow.add_conditional_edges(
        "critic",
        route_after_critic,
        {"revise": "revise", "finalize": "finalize"},
    )
    workflow.add_conditional_edges(
        "revise",
        route_after_revise,
        {"critic": "critic", "finalize": "finalize"},
    )
    workflow.add_edge("finalize", "update_memory")
    workflow.add_edge("update_memory", END)

    return workflow.compile(checkpointer=active_checkpointer, store=active_store)
