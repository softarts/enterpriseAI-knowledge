"""TEST 4: User isolation verification across namespaces in LangGraph Store."""

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
from app.memory import create_memory_store, get_user_memory_namespace, save_user_memory
from test_helpers import DeterministicMockChatModel, KeywordBagEmbeddings


class TestUserIsolation(unittest.TestCase):
    def test_user_b_cannot_access_user_a_memories(self):
        """
        Verify strict tenant/user isolation:
        Memories saved under User A cannot be retrieved or seen by User B.
        """
        embedder = KeywordBagEmbeddings()
        store = create_memory_store(
            embeddings=embedder,
            dims=len(KeywordBagEmbeddings.KEYWORDS),
        )

        # Seed User A memory
        save_user_memory(
            store=store,
            user_id="user_A",
            memory_content="用户喜欢日本料理。",
            thread_id="t_user_a",
        )

        # Confirm User A memory exists in User A namespace
        user_a_ns = get_user_memory_namespace("user_A")
        user_a_items = store.search(user_a_ns)
        self.assertEqual(len(user_a_items), 1)
        self.assertEqual(user_a_items[0].value["content"], "用户喜欢日本料理。")

        # Confirm User B namespace is completely empty
        user_b_ns = get_user_memory_namespace("user_B")
        user_b_items = store.search(user_b_ns)
        self.assertEqual(len(user_b_items), 0)

        # Now run graph invocation for User B
        def mock_llm_response(messages):
            system_msg = messages[0].content
            # If User A's memory leaked into system prompt, flag it
            if "日本料理" in system_msg:
                return "泄漏了用户A的记忆！"
            return "对不起，我还没有关于你喜欢什么料理的记忆。"

        mock_llm = DeterministicMockChatModel(response_generator=mock_llm_response)
        checkpointer = MemorySaver()
        graph = build_memory_graph(
            llm=mock_llm,
            checkpointer=checkpointer,
            store=store,
        )

        config_user_b = {
            "configurable": {
                "thread_id": "thread_B_1",
                "user_id": "user_B",
            }
        }
        turn_b = graph.invoke(
            {"messages": [HumanMessage(content="我喜欢什么料理？")]},
            config=config_user_b,
        )

        # Verified: User B has empty retrieved_memories
        self.assertEqual(turn_b.get("retrieved_memories"), [])
        self.assertNotIn("日本料理", turn_b["messages"][-1].content)
        self.assertIn("还没有关于你喜欢什么料理的记忆", turn_b["messages"][-1].content)


if __name__ == "__main__":
    unittest.main()
