"""ChromaStore 单元测试（临时目录，不依赖真实 vector_db 与 embedding 模型）。

覆盖与 rag_service.retrieve 的集成契约：
    - add_embedded_chunks() 幂等 upsert
    - query() 返回 VectorSearchResult 的字段完整性（retrieval.py 消费的字段）
    - stats() 的 embedding_dimension（回归：Chroma peek 返回 numpy 数组，
      真值判断会抛 ValueError 导致维度永远为 None）
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from embedding_service.models import EmbeddedChunk
from vector_service.chroma_store import ChromaStore


def _chunk(chunk_id: str, vector: list, heading=None) -> EmbeddedChunk:
    return EmbeddedChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        title="Doc One",
        heading=heading,
        content=f"content of {chunk_id}",
        source_path="doc_one.md",
        embedding=vector,
        embedding_model="test-model",
        embedding_dimension=len(vector),
    )


class ChromaStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = ChromaStore(
            db_dir=Path(self._tmpdir.name),
            model="test-model",
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_add_query_roundtrip(self) -> None:
        written = self.store.add_embedded_chunks(
            [
                _chunk("c1", [1.0, 0.0], heading="Intro"),
                _chunk("c2", [0.0, 1.0]),
            ]
        )
        self.assertEqual(written, 2)

        results = self.store.query([1.0, 0.0], top_k=2)
        self.assertEqual(len(results), 2)
        top = results[0]
        # retrieval.py 依赖的字段映射
        self.assertEqual(top.chunk_id, "c1")
        self.assertEqual(top.document_id, "doc-1")
        self.assertEqual(top.title, "Doc One")
        self.assertEqual(top.heading, "Intro")
        self.assertEqual(top.source_path, "doc_one.md")
        self.assertEqual(top.text, "content of c1")
        self.assertEqual(top.rank, 1)
        self.assertLess(top.distance, results[1].distance)
        # None heading 在写入时被强制为空串，读取时还原为 None
        self.assertIsNone(results[1].heading)

    def test_upsert_is_idempotent(self) -> None:
        self.store.add_embedded_chunks([_chunk("c1", [1.0, 0.0])])
        self.store.add_embedded_chunks([_chunk("c1", [0.0, 1.0])])
        stats = self.store.stats()
        self.assertEqual(stats["count"], 1)
        results = self.store.query([0.0, 1.0], top_k=1)
        self.assertAlmostEqual(results[0].distance, 0.0, places=5)

    def test_stats_reports_embedding_dimension(self) -> None:
        """回归：Chroma peek 的 embeddings 是 numpy 数组，stats 不得吞错返回 None。"""
        self.store.add_embedded_chunks([_chunk("c1", [0.5, 0.5, 0.5])])
        stats = self.store.stats()
        self.assertEqual(stats["embedding_dimension"], 3)
        self.assertEqual(stats["count"], 1)
        self.assertEqual(stats["distance_space"], "cosine")
        self.assertEqual(stats["model"], "test-model")

    def test_query_empty_collection_returns_empty(self) -> None:
        self.assertEqual(self.store.query([1.0, 0.0]), [])

    def test_mixed_dimensions_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_embedded_chunks(
                [_chunk("c1", [1.0, 0.0]), _chunk("c2", [1.0, 0.0, 0.0])]
            )


if __name__ == "__main__":
    unittest.main()
