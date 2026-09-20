"""TEST 1: Short-term memory verification via LangGraph State + Checkpointer."""

from __future__ import annotations

import os
import sys
import unittest

_current_dir = os.path.abspath(os.path.dirname(__file__))
_parent_dir = os.path.abspath(os.path.join(_current_dir, ".."))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.graph import build_memory_graph
from test_helpers import DeterministicMockChatModel


class TestShortTermMemory(unittest.TestCase):
    def test_same_thread_preserves_conversation_history(self):
        """
        Verify that within the same thread_id, the Checkpointer restores
        previous conversation state across turns.
        """

        def mock_llm_response(messages):
            # If previous message history contains Alice, answer Alice
            full_context = " ".join(
                str(m.content) for m in messages if hasattr(m, "content")
            )
            if "Alice" in full_context and "叫什么名字" in messages[-1].content:
                return "你叫 Alice。"
            return "收到你的信息。"

        mock_llm = DeterministicMockChatModel(response_generator=mock_llm_response)
        checkpointer = MemorySaver()
        graph = build_memory_graph(llm=mock_llm, checkpointer=checkpointer)

        thread_config = {
            "configurable": {
                "thread_id": "thread_A",
                "user_id": "user_A",
            }
        }

        # Turn 1: User introduces name
        turn1 = graph.invoke(
            {"messages": [HumanMessage(content="我的名字是 Alice。")]},
            config=thread_config,
        )
        self.assertEqual(len(turn1["messages"]), 2)
        self.assertEqual(turn1["messages"][0].content, "我的名字是 Alice。")
        self.assertEqual(turn1["messages"][1].content, "收到你的信息。")

        # Turn 2: User asks for name in the same thread
        turn2 = graph.invoke(
            {"messages": [HumanMessage(content="我叫什么名字？")]},
            config=thread_config,
        )

        # Check that state history accumulated to 4 messages (2 human + 2 AI)
        self.assertEqual(len(turn2["messages"]), 4)
        self.assertEqual(turn2["messages"][0].content, "我的名字是 Alice。")
        self.assertEqual(turn2["messages"][2].content, "我叫什么名字？")
        # Check that assistant answered using previous conversation history
        self.assertIn("Alice", turn2["messages"][-1].content)


if __name__ == "__main__":
    unittest.main()
