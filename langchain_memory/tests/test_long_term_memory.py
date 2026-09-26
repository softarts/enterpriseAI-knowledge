"""TEST 2: Long-term memory verification via LangGraph Store across threads."""

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
from app.memory import create_memory_store
from app.prompts import MemoryExtraction
from test_helpers import DeterministicMockChatModel, KeywordBagEmbeddings


class TestLongTermMemory(unittest.TestCase):
    def test_store_memory_retrieval_across_threads(self):
        """
        Verify that a long-term memory saved in Thread A is retrievable in Thread B
        for the same user_id, once the LLM decides to call `search_memory`.
        """
        embedder = KeywordBagEmbeddings()
        store = create_memory_store(
            embeddings=embedder,
            dims=len(KeywordBagEmbeddings.KEYWORDS),
        )

        def mock_tool_call_rule(messages):
            # The LLM only decides to search memory for a recommendation
            # question, not for a plain preference statement.
            last_human = next(
                (m for m in reversed(messages) if getattr(m, "type", "") == "human"),
                None,
            )
            if last_human and "适合我" in str(last_human.content):
                return {"name": "search_memory", "args": {"query": "餐厅偏好"}}
            return None

        def mock_llm_response(messages):
            # Inspect the ToolMessage produced by search_memory (if any) to
            # verify retrieved long-term memories were passed back to the LLM.
            tool_message = next(
                (m for m in reversed(messages) if getattr(m, "type", "") == "tool"),
                None,
            )
            tool_text = str(getattr(tool_message, "content", "")) if tool_message else ""
            if "安静的餐厅" in tool_text:
                return "根据你的偏好，我推荐安静舒适的日式料理或私房菜餐厅。"
            return "收到你的餐厅偏好。"

        mock_llm = DeterministicMockChatModel(
            response_generator=mock_llm_response,
            tool_call_rule=mock_tool_call_rule,
            extraction_rule=lambda user_text: (
                MemoryExtraction(should_store=True, memory="用户喜欢安静的餐厅。")
                if "安静" in user_text and "餐厅" in user_text
                else MemoryExtraction(should_store=False, memory=None)
            ),
        )

        checkpointer = MemorySaver()
        graph = build_memory_graph(
            llm=mock_llm,
            checkpointer=checkpointer,
            store=store,
        )

        # Thread A: User shares preference (no reason for the LLM to search memory here)
        config_thread_a = {
            "configurable": {
                "thread_id": "thread_A",
                "user_id": "user_A",
            }
        }
        turn_a = graph.invoke(
            {"messages": [HumanMessage(content="我喜欢安静的餐厅。")]},
            config=config_thread_a,
        )
        self.assertEqual(len(turn_a["messages"]), 2)

        # Verify that memory is now stored in Store under ('users', 'user_A', 'memories')
        items = store.search(("users", "user_A", "memories"))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].value["content"], "用户喜欢安静的餐厅。")
        self.assertEqual(items[0].value["source_thread_id"], "thread_A")

        # Thread B: New thread for same user_A asks for recommendation
        config_thread_b = {
            "configurable": {
                "thread_id": "thread_B",  # Separate thread
                "user_id": "user_A",       # Same user
            }
        }
        turn_b = graph.invoke(
            {"messages": [HumanMessage(content="你觉得什么样的餐厅适合我？")]},
            config=config_thread_b,
        )

        # In Thread B this turn adds 4 messages: Human, AI(tool_call), Tool(result), AI(final)
        self.assertEqual(len(turn_b["messages"]), 4)
        tool_messages = [m for m in turn_b["messages"] if getattr(m, "type", "") == "tool"]
        self.assertEqual(len(tool_messages), 1)
        # The LLM decided to call search_memory, which found the long-term memory!
        self.assertIn("用户喜欢安静的餐厅。", tool_messages[0].content)
        # And the assistant's final answer reflects this retrieved background
        self.assertIn("安静舒适", turn_b["messages"][-1].content)


if __name__ == "__main__":
    unittest.main()

