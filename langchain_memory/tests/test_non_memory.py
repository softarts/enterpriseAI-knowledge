"""TEST 5: Non-memory content verification ensuring transient queries are not saved."""

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
from app.memory import create_memory_store, get_user_memory_namespace
from app.prompts import MemoryExtraction
from test_helpers import DeterministicMockChatModel


class TestNonMemoryContent(unittest.TestCase):
    def test_transient_question_does_not_create_memory(self):
        """
        Verify that answering a factual/transient question (e.g. '2 + 2 等于多少？')
        does NOT trigger long-term memory creation.
        """
        store = create_memory_store()

        def mock_llm_response(messages):
            return "2 + 2 等于 4。"

        def mock_extraction(user_text):
            # Transient / factual question: should NOT store memory
            if "2 + 2" in user_text:
                return MemoryExtraction(should_store=False, memory=None)
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

        user_id = "user_calc_test"
        thread_config = {
            "configurable": {
                "thread_id": "thread_calc",
                "user_id": user_id,
            }
        }

        turn = graph.invoke(
            {"messages": [HumanMessage(content="2 + 2 等于多少？")]},
            config=thread_config,
        )

        # Assistant answered correctly
        self.assertIn("等于 4", turn["messages"][-1].content)

        # Verified: Store namespace for this user remains completely empty!
        namespace = get_user_memory_namespace(user_id)
        stored_items = store.search(namespace)
        self.assertEqual(len(stored_items), 0)


if __name__ == "__main__":
    unittest.main()
