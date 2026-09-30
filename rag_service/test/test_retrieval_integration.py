"""rag_service ↔ vector_service 真实集成冒烟测试（非 mock）。

使用项目根目录下真实的 vector_db/（Chroma PersistentClient）与真实
bge-m3 embedder 端到端验证 retrieve() 链路。vector_db 不存在时跳过；
首次运行需加载 bge-m3 模型（约数秒）。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from rag_service import config, retrieval

_VECTOR_DB = Path(__file__).resolve().parents[2] / "vector_db" / "chroma.sqlite3"


@unittest.skipUnless(_VECTOR_DB.exists(), "vector_db 不存在，跳过真实集成测试")
class RetrievalIntegrationTest(unittest.TestCase):
    def test_retrieve_end_to_end(self) -> None:
        chunks = retrieval.retrieve("部署流程是什么？", k=config.TOP_K)

        self.assertEqual(len(chunks), config.TOP_K)
        # 距离升序（rank 1-indexed）
        distances = [c.distance for c in chunks]
        self.assertEqual(distances, sorted(distances))
        self.assertEqual([c.rank for c in chunks], list(range(1, len(chunks) + 1)))
        # graph.retrieve_node / prompt_builder 消费的字段完整性
        for c in chunks:
            self.assertTrue(c.chunk_id)
            self.assertTrue(c.document_id)
            self.assertTrue(c.title)
            self.assertTrue(c.source_path)
            self.assertTrue(c.text.strip())
        # is_confident 返回布尔且不抛异常
        self.assertIsInstance(retrieval.is_confident(chunks), bool)

    def test_stats_dimension_matches_embedder(self) -> None:
        """collection 向量维度必须等于 embedder 输出维度（bge-m3 = 1024）。"""
        from vector_service.chroma_store import ChromaStore

        stats = ChromaStore(model=config.EMBEDDING_MODEL).stats()
        vec = retrieval._get_embedder().embed_query("dimension probe")
        self.assertGreater(stats["count"], 0)
        self.assertEqual(stats["embedding_dimension"], len(vec))

    def test_empty_query_returns_empty(self) -> None:
        self.assertEqual(retrieval.retrieve(""), [])
        self.assertFalse(retrieval.is_confident([]))


if __name__ == "__main__":
    unittest.main()
