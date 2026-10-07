"""LangGraph state definition."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Represents a tool call from the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]


class AgentState(BaseModel):
    """State for the LangGraph agent."""
    
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    """Chat messages history."""
    
    tool_calls: List[ToolCall] = Field(default_factory=list)
    """Pending tool calls to execute."""
    
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)
    """Results from tool executions."""
    
    final_answer: Optional[str] = None
    """Final answer to return to user."""
    
    user_id: str = "1234"
    """User ID for memory isolation."""
    
    trace_id: Optional[str] = None
    """Trace ID for this conversation turn."""
    
    class Config:
        """Pydantic config."""
        arbitrary_types_allowed = True