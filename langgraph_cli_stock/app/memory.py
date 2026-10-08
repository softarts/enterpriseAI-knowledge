"""Memory module for LangGraph with short-term and long-term memory."""

import logging
from typing import Any, Dict, List, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


class MemoryManager:
    """Manages both short-term (checkpointer) and long-term (store) memory."""
    
    def __init__(self, user_id: str):
        """Initialize memory manager for a specific user."""
        self.user_id = user_id
        self.checkpointer = MemorySaver()
        self.store = InMemoryStore()
        
        # Initialize namespace for user
        self._user_namespace = (user_id,)
    
    def save_conversation(self, thread_id: str, messages: List[Dict[str, Any]]):
        """Save conversation messages to short-term memory."""
        # This is handled by LangGraph checkpointer automatically
        # We just provide the checkpointer instance
        pass
    
    def get_conversation_history(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get conversation history from short-term memory."""
        # This will be handled by the graph's checkpointer
        return []
    
    def save_to_long_term(self, key: str, value: Any):
        """Save data to long-term memory (in-memory store)."""
        self.store.put(self._user_namespace, key, {"data": value})
    
    def get_from_long_term(self, key: str) -> Optional[Any]:
        """Get data from long-term memory."""
        result = self.store.get(self._user_namespace, key)
        if result:
            return result.value.get("data")
        return None
    
    def list_long_term_memory(self) -> List[str]:
        """List all keys in long-term memory for this user."""
        return [item.key for item in self.store.search(self._user_namespace)]


def create_memory_manager(user_id: str) -> MemoryManager:
    """Factory function to create a memory manager."""
    return MemoryManager(user_id)


def log_memory_operation(
    logger: logging.Logger,
    operation: str,
    trace_id: str,
    user_id: str,
    details: Dict[str, Any] = None
):
    """Log memory operations."""
    extra = {
        "trace_id": trace_id,
        "event_type": "memory_operation",
        "component": "memory",
        "payload": {
            "operation": operation,
            "user_id": user_id,
            "details": details or {}
        }
    }
    logger.info(f"Memory operation: {operation}", extra=extra)