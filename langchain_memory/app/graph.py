"""LangGraph workflow definition for Conversational Memory MVP V1."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore

try:
    from . import config as app_config
    from .memory import (
        create_memory_store,
        create_search_memory_tool,
        extract_and_save_memory,
    )
    from .prompts import BASE_SYSTEM_PROMPT, MemoryExtraction
    from .state import MemoryGraphState
except ImportError:  # pragma: no cover - supports direct app/ test execution
    from app import config as app_config
    from app.memory import (
        create_memory_store,
        create_search_memory_tool,
        extract_and_save_memory,
    )
    from app.prompts import BASE_SYSTEM_PROMPT, MemoryExtraction
    from app.state import MemoryGraphState



logger = logging.getLogger(__name__)


def _has_pending_tool_calls(state: MemoryGraphState) -> bool:
    """Whether the last message is an AIMessage requesting a tool call."""
    messages = state.get("messages", [])
    if not messages:
        return False
    return bool(getattr(messages[-1], "tool_calls", None))


def create_agent_node(llm: BaseChatModel, tools: Sequence[BaseTool]):
    """
    Agent node: the LLM sees the full thread history and decides, on its own,
    whether to call a tool (e.g. `search_memory`) or answer directly.
    """

    llm_with_tools = llm.bind_tools(tools)

    def agent(
        state: MemoryGraphState,
        config: RunnableConfig,
    ) -> Dict[str, Any]:
        conversation_messages = list(state.get("messages", []))
        if conversation_messages and isinstance(conversation_messages[0], SystemMessage):
            existing_prompt = str(conversation_messages[0].content)
            if not existing_prompt.startswith(BASE_SYSTEM_PROMPT):
                conversation_messages[0] = SystemMessage(
                    content=f"{BASE_SYSTEM_PROMPT}\n\n{existing_prompt}"
                )
        else:
            conversation_messages.insert(0, SystemMessage(content=BASE_SYSTEM_PROMPT))
        response = llm_with_tools.invoke(conversation_messages, config=config)
        return {"messages": [response]}

    return agent


def create_update_memory_node(llm: BaseChatModel):
    """Write-back node: extract and persist long-term memories using structured LLM output.

    This node is never exposed to the LLM as a tool; it always runs after the
    agent has produced its final reply.
    """

    extraction_llm = llm.with_structured_output(MemoryExtraction)

    def update_memory(
        state: MemoryGraphState,
        config: RunnableConfig,
        *,
        store: BaseStore,
    ) -> Dict[str, Any]:
        configurable = config.get("configurable", {})
        user_id: Optional[str] = configurable.get("user_id")
        thread_id: Optional[str] = configurable.get("thread_id")

        if not user_id or store is None:
            return {}

        messages = state.get("messages", [])
        if not messages:
            return {}

        # Identify latest user message and its ID
        latest_user_content: Optional[str] = None
        latest_user_id: Optional[str] = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) or (
                hasattr(msg, "type") and msg.type == "human"
            ):
                latest_user_content = (
                    msg.content if isinstance(msg.content, str) else str(msg.content)
                )
                latest_user_id = getattr(msg, "id", None)
                break

        if not latest_user_content:
            return {}

        try:
            extract_and_save_memory(
                store=store,
                user_id=user_id,
                extraction_llm=extraction_llm,
                extraction_input=f"用户输入: {latest_user_content}",
                thread_id=thread_id,
                message_id=latest_user_id,
            )
        except Exception as exc:
            # Memory extraction or write failure is a non-critical error:
            # log and do not break conversational response
            logger.warning(
                "Memory extraction failed for user '%s': %s",
                user_id,
                exc,
                exc_info=True,
            )

        return {}

    return update_memory


def build_memory_agent_graph(
    llm: BaseChatModel,
    store: BaseStore,
    tools: Sequence[BaseTool],
) -> CompiledStateGraph:
    """
    Agent + tools loop with no write-back node. The final AI response is
    produced by the same model that decides whether to call a tool.

    Flow: START -> agent <-> tools; agent without tool calls -> END
    """
    workflow = StateGraph(MemoryGraphState)
    workflow.add_node("agent", create_agent_node(llm, tools))
    workflow.add_node("tools", ToolNode(list(tools)))

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        lambda state: "tools" if _has_pending_tool_calls(state) else END,
        {"tools": "tools", END: END},
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile(store=store)


def build_memory_graph(
    llm: Optional[BaseChatModel] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    store: Optional[BaseStore] = None,
    top_k: int = app_config.DEFAULT_TOP_K,
) -> CompiledStateGraph:
    """
    Construct and compile the LangGraph Memory workflow.

    Flow:
        START -> agent --(tool_calls)--> tools -> agent (loop)
                 agent --(no tool_calls)--> update_memory -> END

    The LLM bound to the `agent` node decides on its own, per turn, whether to
    call the `search_memory` tool and what query to search with; there is no
    fixed retrieval node and no hardcoded query-rewriting heuristic.
    """
    active_llm = llm or app_config.get_chat_model()
    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()
    active_store = store if store is not None else create_memory_store(
        embeddings=app_config.get_embeddings(),
        dims=app_config.EMBEDDING_DIMS,
    )
    tools: List[BaseTool] = [create_search_memory_tool(top_k)]

    workflow = StateGraph(MemoryGraphState)

    # Register nodes
    workflow.add_node("agent", create_agent_node(active_llm, tools))
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_node("update_memory", create_update_memory_node(active_llm))

    # Agent decides whether to call a tool or finish and hand off to the
    # (non-tool) write-back node.
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        lambda state: "tools" if _has_pending_tool_calls(state) else "update_memory",
        {"tools": "tools", "update_memory": "update_memory"},
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("update_memory", END)

    return workflow.compile(checkpointer=active_checkpointer, store=active_store)

