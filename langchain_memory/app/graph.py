"""LangGraph workflow: short-term checkpointer memory + long-term memory agent.

Graph assembly only. Long-term memory logic (store factory, retrieval, write,
structured extraction, tool creation) lives in app/long_memory.py and is
imported here; short-term history stays owned by the Checkpointer.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
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
    from .long_memory import (
        create_memory_store,
        create_search_memory_tool,
        extract_and_save_memory,
    )
    from .long_memory_prompts import MemoryExtraction
    from .prompts import BASE_SYSTEM_PROMPT
    from .state import MemoryGraphState
except ImportError:  # pragma: no cover - supports direct app/ test execution
    from app import config as app_config
    from app.long_memory import (
        create_memory_store,
        create_search_memory_tool,
        extract_and_save_memory,
    )
    from app.long_memory_prompts import MemoryExtraction
    from app.prompts import BASE_SYSTEM_PROMPT
    from app.state import MemoryGraphState

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d - %(message)s"
)


def create_agent_node(
    llm: BaseChatModel,
    system_prompt: Optional[str] = None,
    tools: Optional[Sequence[BaseTool]] = None,
):
    """Create an agent that adds system instructions without storing them.

    Tools are bound to the LLM here; whether to call them is decided by the
    model inside the tool-calling loop, never by pre-retrieval in a pipeline.
    """
    system_content = BASE_SYSTEM_PROMPT
    if system_prompt:
        system_content = f"{BASE_SYSTEM_PROMPT}\n\n{system_prompt}"
    llm_with_tools = llm.bind_tools(list(tools)) if tools else llm

    def agent(
        state: MemoryGraphState,
        config: RunnableConfig,
    ) -> Dict[str, Any]:
        messages = state["messages"]
        configurable = config.get("configurable", {})
        logger.info(
            "memory.agent.invoke thread_id=%s message_count=%d message_types=%s",
            configurable.get("thread_id"),
            len(messages),
            [getattr(message, "type", type(message).__name__) for message in messages],
        )
        system = SystemMessage(content=system_content)
        response = llm_with_tools.invoke([system] + messages, config=config)
        logger.info(
            "memory.agent.completed thread_id=%s response_type=%s tool_calls=%d",
            configurable.get("thread_id"),
            getattr(response, "type", type(response).__name__),
            len(getattr(response, "tool_calls", None) or []),
        )
        return {"messages": [response]}

    return agent


def should_continue(state: MemoryGraphState) -> str:
    """Route to tools while the last AI message requests tool calls."""
    # print("=" * 30, "should_continue stack trace", "=" * 30)
    # print("".join(traceback.format_stack()[:-1]))
    logger.info("should_continue Route to tools while the last AI message requests tool calls.")

    last_message = state["messages"][-1]
    print("should_continue => check last_message: %s\n", last_message)
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "update_memory"


def create_update_memory_node(llm: BaseChatModel):
    """Create the post-answer long-term memory write node.

    The node runs after the agent produced its final answer; it is not a tool
    and is never visible to the LLM. Extraction uses structured output, and
    any failure is logged without interrupting the answered turn.
    """
    extraction_llm = llm.with_structured_output(MemoryExtraction)

    def update_memory(
        state: MemoryGraphState,
        config: RunnableConfig,
        *,
        store: BaseStore,
    ) -> Dict[str, Any]:
        logger.info("*** update_memory. ***")
        
        configurable = config.get("configurable", {})
        user_id = configurable.get("user_id")
        thread_id = configurable.get("thread_id")
        if not user_id:
            logger.info(
                "memory.longterm.update.skip thread_id=%s reason=no_user_id",
                thread_id,
            )
            return {}
        latest_human: Optional[HumanMessage] = None
        for message in reversed(state["messages"]):
            if isinstance(message, HumanMessage):
                latest_human = message
                break
        if latest_human is None or not str(latest_human.content).strip():
            return {}
        try:
            saved = extract_and_save_memory(
                store=store,
                user_id=user_id,
                extraction_llm=extraction_llm,
                extraction_input=str(latest_human.content),
                thread_id=thread_id,
                message_id=latest_human.id,
            )
            logger.info(
                "memory.longterm.update.completed thread_id=%s user_id=%s saved=%s",
                thread_id,
                user_id,
                saved,
            )
        except Exception:
            logger.warning(
                "memory.longterm.update.failed thread_id=%s user_id=%s",
                thread_id,
                user_id,
                exc_info=True,
            )
        return {}

    return update_memory


def build_memory_agent_graph(
    llm: Optional[BaseChatModel] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    system_prompt: Optional[str] = None,
    store: Optional[BaseStore] = None,
    tools: Optional[List[BaseTool]] = None,
) -> CompiledStateGraph:
    """Build the agent graph with checkpointer (short-term) and store (V2).

    Control flow: START -> agent; agent loops with the tools node while the
    model requests tool calls; once the model answers, update_memory runs the
    structured long-term memory extraction, then END.
    """
    active_llm = llm or app_config.get_chat_model()
    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()
    active_store = store if store is not None else create_memory_store()
    active_tools: List[BaseTool] = (
        list(tools)
        if tools is not None
        else [create_search_memory_tool(default_top_k=app_config.MEMORY_TOP_K)]
    )

    workflow = StateGraph(MemoryGraphState)
    workflow.add_node(
        "agent",
        create_agent_node(active_llm, system_prompt=system_prompt, tools=active_tools),
    )
    workflow.add_node("tools", ToolNode(active_tools))
    workflow.add_node("update_memory", create_update_memory_node(active_llm))
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "update_memory": "update_memory"},
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("update_memory", END)

    return workflow.compile(checkpointer=active_checkpointer, store=active_store)
