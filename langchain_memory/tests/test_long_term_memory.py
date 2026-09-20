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
        for the same user_id.
        """
        embedder = KeywordBagEmbeddings()
        store = create_memory_store(
            embeddings=embedder,
            dims=len(KeywordBagEmbeddings.KEYWORDS),
        )

        def mock_llm_response(messages):
            # Inspect system prompt to verify retrieved long-term memories were passed
            system_msg = messages[0].content
            if "安静的餐厅" in system_msg:
                return "根据你的偏好，我推荐安静舒适的日式料理或私房菜餐厅。"
            return "收到你的餐厅偏好。"

        def mock_extraction(user_text):
            if "安静" in user_text and "餐厅" in user_text:
                return MemoryExtraction(should_store=True, memory="用户喜欢安静的餐厅。")
            return MemoryExtraction(should_store=False, memory=None)

        mock_llm = DeterministicMockChatModel(
            response_generator=mock_llm_response,
            extraction_rule=mock_extraction,
        )

        checkpointer = MemorySaver()
        graph = build_memory_graph(
            llm=mock_llm,
            checkpointer=checkpointer,
            store=store,
        )

        # Thread A: User shares preference
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

        # In Thread B, short-term history only has 2 messages (no Thread A messages)
        self.assertEqual(len(turn_b["messages"]), 2)
        # But retrieved_memories in graph state contains the long-term memory!
        self.assertIn("用户喜欢安静的餐厅。", turn_b["retrieved_memories"])
        # And the assistant's answer reflects this retrieved background
        self.assertIn("安静舒适", turn_b["messages"][-1].content)


if __name__ == "__main__":
    unittest.main()
