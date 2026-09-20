"""TEST 3: Semantic retrieval verification via LangGraph Store vector search."""

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

from app.memory import create_memory_store, retrieve_user_memories, save_user_memory
from test_helpers import KeywordBagEmbeddings


class TestSemanticRetrieval(unittest.TestCase):
    def test_semantic_search_finds_relevant_memory(self):
        """
        Verify that semantic search over LangGraph Store successfully matches
        a paraphrase/related query to stored memory.
        """
        embedder = KeywordBagEmbeddings()
        store = create_memory_store(
            embeddings=embedder,
            dims=len(KeywordBagEmbeddings.KEYWORDS),
        )

        user_id = "user_semantic_test"

        # Pre-populate store with two memories: one relevant, one irrelevant
        save_user_memory(
            store=store,
            user_id=user_id,
            memory_content="用户喜欢安静的餐厅。",
            thread_id="t_seed",
        )
        save_user_memory(
            store=store,
            user_id=user_id,
            memory_content="用户在新加坡工作。",
            thread_id="t_seed",
        )

        # Query using a semantic variation
        query = "帮我找一家比较安静、适合吃晚饭的地方。"
        retrieved = retrieve_user_memories(
            store=store,
            user_id=user_id,
            query=query,
            top_k=2,
        )

        # Verify semantic retrieval functional link works
        self.assertGreaterEqual(len(retrieved), 1)
        # The first hit should be the relevant dining preference
        self.assertEqual(retrieved[0], "用户喜欢安静的餐厅。")


if __name__ == "__main__":
    unittest.main()
