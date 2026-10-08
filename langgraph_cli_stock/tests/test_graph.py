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


class TestToolCallHandling(unittest.TestCase):
    """Test parsing and executing LLM tool calls."""

    def test_model_prompt_includes_current_date_for_relative_dates(self):
        from app.graph import model_node
        from app.state import AgentState

        client = MagicMock()
        client.chat.return_value = {
            "choices": [{"message": {"content": "查询 AAPL 昨天的收盘价。"}}]
        }

        with (
            patch("app.graph.get_llm_client", return_value=client),
            patch("app.graph._get_current_date", return_value="2026-10-08")
        ):
            model_node(AgentState(
                messages=[{"role": "user", "content": "昨天"}],
                trace_id="test-trace"
            ))

        system_prompt = client.chat.call_args.kwargs["messages"][0]["content"]
        self.assertIn("Today's date is 2026-10-08", system_prompt)
        self.assertIn("昨天", system_prompt)
        self.assertIn("retain the stock symbol", system_prompt)

    def test_graph_parses_json_arguments_and_executes_tool_call(self):
        from app.graph import run_agent

        client = MagicMock()
        client.chat.side_effect = [
            {
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "id": "call-1",
                            "function": {
                                "name": "stock_price",
                                "arguments": '{"symbol":"AAPL","date":"2024-11-27"}'
                            }
                        }]
                    }
                }]
            },
            {"choices": [{"message": {"content": "Apple closed at $123.45."}}]}
        ]

        with (
            patch("app.graph.get_llm_client", return_value=client),
            patch("app.graph.execute_tool", return_value={"close": 123.45}) as execute_tool
        ):
            answer = run_agent(
                "What was Apple's closing price?",
                user_id="test-user",
                trace_id="test-trace",
                thread_id="test-tool-call-thread"
            )

        self.assertEqual(
            execute_tool.call_args.args[:2],
            (
                "stock_price",
                {"symbol": "AAPL", "date": "2024-11-27"}
            )
        )
        self.assertEqual(answer, "Apple closed at $123.45.")

    def test_model_node_rejects_invalid_json_arguments(self):
        from app.graph import model_node
        from app.state import AgentState

        client = MagicMock()
        client.chat.return_value = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call-1",
                        "function": {
                            "name": "stock_price",
                            "arguments": '{"symbol":'
                        }
                    }]
                }
            }]
        }

        with patch("app.graph.get_llm_client", return_value=client):
            with self.assertRaisesRegex(ValueError, "valid JSON"):
                model_node(AgentState(trace_id="test-trace"))


class TestConversationContinuity(unittest.TestCase):
    def test_run_agent_includes_prior_turns(self):
        from app.graph import run_agent

        graph = MagicMock()
        graph.invoke.return_value = {
            "final_answer": "The date is 2024-11-27.",
            "tool_calls": [],
            "tool_results": []
        }
        history = [
            {"role": "user", "content": "aapl的收盘价"},
            {"role": "assistant", "content": "请提供日期。"}
        ]

        with patch("app.graph.get_graph", return_value=graph):
            answer = run_agent(
                "昨天",
                user_id="test-user",
                trace_id="test-trace",
                thread_id="test-thread",
                conversation_history=history
            )

        self.assertEqual(answer, "The date is 2024-11-27.")
        self.assertEqual(
            graph.invoke.call_args.args[0].messages,
            history + [{"role": "user", "content": "昨天"}]
        )

    def test_cli_passes_and_saves_conversation_history(self):
        from app.cli import CLI

        cli = CLI("test-user")
        with (
            patch("builtins.input", side_effect=["aapl的收盘价", "昨天", "/exit"]),
            patch("app.cli.run_agent", side_effect=["请提供日期。", "AAPL 昨天收盘价为 $100。"]) as run_agent,
            patch("app.cli.setup_logging", return_value=MagicMock()),
            patch("app.cli.generate_trace_id", side_effect=["trace-1", "trace-2"]),
            patch.object(cli, "print_welcome"),
            self.assertRaises(SystemExit)
        ):
            cli.run()

        self.assertEqual(
            run_agent.call_args_list[1].kwargs["conversation_history"],
            [
                {"role": "user", "content": "aapl的收盘价"},
                {"role": "assistant", "content": "请提供日期。"}
            ]
        )
        self.assertEqual(
            cli.memory.get_conversation_history("test-user"),
            [
                {"role": "user", "content": "aapl的收盘价"},
                {"role": "assistant", "content": "请提供日期。"},
                {"role": "user", "content": "昨天"},
                {"role": "assistant", "content": "AAPL 昨天收盘价为 $100。"}
            ]
        )


class TestMemory(unittest.TestCase):
    """Test memory management."""
    
    def test_memory_manager_creation(self):
        """Test memory manager can be created."""
        from app.memory import create_memory_manager, MemoryManager
        
        memory = create_memory_manager("user123")
        
        self.assertIsInstance(memory, MemoryManager)
        self.assertEqual(memory.user_id, "user123")

    def test_conversation_history_can_be_saved_loaded_and_cleared(self):
        from app.memory import create_memory_manager

        memory = create_memory_manager("user123")
        messages = [{"role": "user", "content": "AAPL close"}]
        memory.save_conversation("thread-1", messages)
        messages.append({"role": "assistant", "content": "Which date?"})

        self.assertEqual(
            memory.get_conversation_history("thread-1"),
            [{"role": "user", "content": "AAPL close"}]
        )
        memory.clear_conversation("thread-1")
        self.assertEqual(memory.get_conversation_history("thread-1"), [])
    
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