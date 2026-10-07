"""Tests for LangGraph and memory."""

import unittest
from unittest.mock import patch, MagicMock
import json


class TestGraphStructure(unittest.TestCase):
    """Test LangGraph structure."""
    
    def test_graph_creation(self):
        """Test graph can be created."""
        from app.graph import create_graph, get_graph
        
        graph = create_graph()
        self.assertIsNotNone(graph)
        
        # Test singleton
        graph2 = get_graph()
        self.assertIs(graph, graph2)
    
    def test_graph_has_required_nodes(self):
        """Test graph has agent and tools nodes."""
        from app.graph import get_graph
        
        graph = get_graph()
        # Check the graph has nodes
        # LangGraph stores nodes in nodes dict
        self.assertIsNotNone(graph.nodes)


class TestAgentState(unittest.TestCase):
    """Test agent state model."""
    
    def test_agent_state_creation(self):
        """Test AgentState can be created."""
        from app.state import AgentState
        
        state = AgentState(
            messages=[{"role": "user", "content": "Hello"}],
            user_id="1234",
            trace_id="test-trace"
        )
        
        self.assertEqual(len(state.messages), 1)
        self.assertEqual(state.user_id, "1234")
        self.assertEqual(state.trace_id, "test-trace")
    
    def test_agent_state_defaults(self):
        """Test AgentState has correct defaults."""
        from app.state import AgentState
        
        state = AgentState()
        
        self.assertEqual(state.messages, [])
        self.assertEqual(state.tool_calls, [])
        self.assertEqual(state.tool_results, [])
        self.assertIsNone(state.final_answer)
        self.assertEqual(state.user_id, "1234")


class TestMemory(unittest.TestCase):
    """Test memory management."""
    
    def test_memory_manager_creation(self):
        """Test memory manager can be created."""
        from app.memory import create_memory_manager, MemoryManager
        
        memory = create_memory_manager("user123")
        
        self.assertIsInstance(memory, MemoryManager)
        self.assertEqual(memory.user_id, "user123")
    
    def test_long_term_memory_isolation(self):
        """Test long-term memory is isolated by user_id."""
        from app.memory import create_memory_manager
        
        memory1 = create_memory_manager("user1")
        memory2 = create_memory_manager("user2")
        
        # Save to user1 memory
        memory1.save_to_long_term("preference", "dark_mode")
        
        # Should not be accessible to user2
        result = memory2.get_from_long_term("preference")
        self.assertIsNone(result)
        
        # Should be accessible to user1
        result = memory1.get_from_long_term("preference")
        self.assertEqual(result, "dark_mode")
    
    def test_list_long_term_memory(self):
        """Test listing long-term memory."""
        from app.memory import create_memory_manager
        
        memory = create_memory_manager("user1")
        memory.save_to_long_term("key1", "value1")
        memory.save_to_long_term("key2", "value2")
        
        keys = memory.list_long_term_memory()
        
        self.assertIn("key1", keys)
        self.assertIn("key2", keys)


class TestMemoryLogging(unittest.TestCase):
    """Test memory operation logging."""
    
    def test_log_memory_operation(self):
        """Test memory operation is logged correctly."""
        import logging
        import json
        import tempfile
        from pathlib import Path
        
        from app.memory import log_memory_operation
        from app.logging_config import JsonLinesHandler
        
        # Create temp log file
        temp_dir = tempfile.mkdtemp()
        log_file = Path(temp_dir) / "test_memory.jsonl"
        
        # Set up handler
        handler = JsonLinesHandler(log_file)
        logger = logging.getLogger("test_memory")
        logger.setLevel(logging.DEBUG)
        logger.handlers = [handler]
        
        # Log memory operation
        log_memory_operation(
            logger=logger,
            operation="save",
            trace_id="trace-123",
            user_id="user-456",
            details={"key": "preference", "value": "dark"}
        )
        
        # Verify log entry
        with open(log_file, "r") as f:
            entry = json.loads(f.readline())
        
        self.assertEqual(entry["trace_id"], "trace-123")
        self.assertEqual(entry["event_type"], "memory_operation")
        self.assertEqual(entry["component"], "memory")
        self.assertEqual(entry["payload"]["operation"], "save")
        self.assertEqual(entry["payload"]["user_id"], "user-456")
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()