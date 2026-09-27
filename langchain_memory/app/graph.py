"""LangGraph workflow for short-term conversational memory."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

try:
    from . import config as app_config
    from .prompts import BASE_SYSTEM_PROMPT
    from .state import MemoryGraphState
except ImportError:  # pragma: no cover - supports direct app/ test execution
    from app import config as app_config
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
):
    """Create an agent that adds system instructions without storing them."""
    system_content = BASE_SYSTEM_PROMPT
    if system_prompt:
        system_content = f"{BASE_SYSTEM_PROMPT}\n\n{system_prompt}"

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
        response = llm.invoke([system] + messages, config=config)
        logger.info(
            "memory.agent.completed thread_id=%s response_type=%s",
            configurable.get("thread_id"),
            getattr(response, "type", type(response).__name__),
        )
        return {"messages": [response]}

    return agent


def build_memory_agent_graph(
    llm: Optional[BaseChatModel] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    system_prompt: Optional[str] = None,
) -> CompiledStateGraph:
    """Build a single-agent graph whose message state is checkpointed by thread."""
    active_llm = llm or app_config.get_chat_model()
    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()

    workflow = StateGraph(MemoryGraphState)
    workflow.add_node("agent", create_agent_node(active_llm, system_prompt=system_prompt))
    workflow.add_edge(START, "agent")
    workflow.add_edge("agent", END)

    return workflow.compile(checkpointer=active_checkpointer)
