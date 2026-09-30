"""Graph State definition for LangGraph Memory MVP V1."""

from __future__ import annotations

from typing import List, TypedDict
from typing_extensions import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class MemoryGraphState(TypedDict):
    """
    State schema for the conversational memory graph.

    - messages: Thread-level short-term conversation history, managed via
      add_messages reducer. Long-term memory search results are ToolMessage
      entries produced by the `search_memory` tool inside this same list; the
      LLM decides whether/when they are needed, so no separate
      `retrieved_memories` field is kept in state.
    """

    messages: Annotated[List[BaseMessage], add_messages]

