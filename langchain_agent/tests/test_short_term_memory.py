"""Short-term memory verification via LangGraph Checkpointer."""

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

from app.graph import build_memory_agent_graph
from test_helpers import DeterministicMockChatModel, create_test_store


class TestShortTermMemory(unittest.TestCase):
    def test_same_thread_preserves_conversation_history(self) -> None:
        def mock_llm_response(messages):
            full_context = " ".join(
                str(message.content) for message in messages if hasattr(message, "content")
            )
            if "Alice" in full_context and "叫什么名字" in messages[-1].content:
                return "你叫 Alice。"
            return "收到你的信息。"

        graph = build_memory_agent_graph(
            llm=DeterministicMockChatModel(response_generator=mock_llm_response),
            checkpointer=MemorySaver(),
            store=create_test_store(),
        )
        thread_config = {"configurable": {"thread_id": "thread_A", "user_id": "user_test"}}

        first_turn = graph.invoke(
            {"messages": [HumanMessage(content="我的名字是 Alice。")]},
            config=thread_config,
        )
        second_turn = graph.invoke(
            {"messages": [HumanMessage(content="我叫什么名字？")]},
            config=thread_config,
        )

        self.assertEqual(len(first_turn["messages"]), 2)
        self.assertEqual(len(second_turn["messages"]), 4)
        self.assertEqual(second_turn["messages"][0].content, "我的名字是 Alice。")
        self.assertEqual(second_turn["messages"][2].content, "我叫什么名字？")
        self.assertIn("Alice", second_turn["messages"][-1].content)
        self.assertTrue(
            all(message.type != "system" for message in second_turn["messages"])
        )

    def test_different_threads_do_not_share_history(self) -> None:
        graph = build_memory_agent_graph(
            llm=DeterministicMockChatModel(default_response="回复"),
            checkpointer=MemorySaver(),
            store=create_test_store(),
        )
        graph.invoke(
            {"messages": [HumanMessage(content="仅在 A 的内容")]},
            config={"configurable": {"thread_id": "thread_A", "user_id": "user_test"}},
        )

        thread_b_state = graph.invoke(
            {"messages": [HumanMessage(content="B 的新对话")]},
            config={"configurable": {"thread_id": "thread_B", "user_id": "user_test"}},
        )

        self.assertEqual(len(thread_b_state["messages"]), 2)
        self.assertEqual(thread_b_state["messages"][0].content, "B 的新对话")


if __name__ == "__main__":
    unittest.main()
