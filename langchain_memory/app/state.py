"""Graph State definition for LangGraph Memory MVP V1."""

from __future__ import annotations

from typing import List, TypedDict
from typing_extensions import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class MemoryGraphState(TypedDict):
    """
    State schema for the conversational memory graph.

    - messages: Thread-level short-term conversation history, managed via add_messages reducer.
    - retrieved_memories: User-level long-term memories retrieved from LangGraph Store for the current turn.
    """

    messages: Annotated[List[BaseMessage], add_messages]
    retrieved_memories: List[str]

