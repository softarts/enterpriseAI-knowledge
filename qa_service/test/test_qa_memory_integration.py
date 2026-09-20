from __future__ import annotations

from typing import Any
import unittest
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import MemorySaver

from langchain_memory.app.memory import create_memory_store, save_user_memory
from langchain_memory.app.prompts import MemoryExtraction
from langchain_memory.app.runtime import create_memory_runtime
from langchain_memory import MemoryContext
from langchain_memory.tests.test_helpers import KeywordBagEmbeddings
from chat_service.api.routes_ask import ask
from chat_service.services.qa.models import AskRequest
from qa_service import pipeline
from qa_service.models import RetrievedChunk


class ExtractionModel:
    def __init__(self, extraction: MemoryExtraction) -> None:
        self.extraction = extraction

    def with_structured_output(self, schema: Any) -> "ExtractionModel":
        return self

    def invoke(self, messages: Any) -> MemoryExtraction:
        return self.extraction


class FailingWriteStore:
    def search(self, *args: Any, **kwargs: Any) -> list:
        return []

    def put(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("write failed")


def _runtime() -> Any:
    store = create_memory_store(
        embeddings=KeywordBagEmbeddings(),
        dims=len(KeywordBagEmbeddings.KEYWORDS),
    )
    return create_memory_runtime(store=store, checkpointer=MemorySaver())


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        title="Test document",
        heading=None,
        source_path="test.md",
        text="企业知识库内容。",
        distance=0.1,
        rank=1,
    )


def _run_answer(question: str, runtime: Any, user_id: str, thread_id: str) -> str:
    with patch.object(pipeline.retrieval, "retrieve", return_value=[_chunk()]), patch.object(
        pipeline.retrieval, "is_confident", return_value=True
    ), patch.object(pipeline.config, "is_reflection_enabled", return_value=False), patch.object(
        pipeline.llm_client, "generate", side_effect=lambda system, context, query: context
    ), patch(
        "langchain_memory.app.config.get_chat_model",
        return_value=ExtractionModel(MemoryExtraction(should_store=False, memory=None)),
    ):
        return pipeline.answer_question(
            question,
            user_id=user_id,
            thread_id=thread_id,
            memory_runtime=runtime,
        ).answer


class TestQAMemoryIntegration(unittest.TestCase):
    def test_same_thread_context_is_sent_to_existing_qa_llm(self) -> None:
        runtime = _runtime()
        _run_answer("我的名字是 Alice。", runtime, "user-a", "thread-a")

        answer = _run_answer("我叫什么名字？", runtime, "user-a", "thread-a")

        self.assertIn("用户: 我的名字是 Alice。", answer)
        self.assertIn("ENTERPRISE KNOWLEDGE:", answer)

    def test_same_thread_follow_up_uses_recent_user_turn_for_retrieval(self) -> None:
        runtime = _runtime()
        _run_answer("How does the organization recognize revenue?", runtime, "user-a", "thread-a")

        with patch.object(pipeline.retrieval, "retrieve", return_value=[_chunk()]) as retrieve, patch.object(
            pipeline.retrieval, "is_confident", return_value=True
        ), patch.object(pipeline.config, "is_reflection_enabled", return_value=False), patch.object(
            pipeline.llm_client, "generate", return_value="正常答案"
        ), patch(
            "langchain_memory.app.config.get_chat_model",
            return_value=ExtractionModel(MemoryExtraction(should_store=False, memory=None)),
        ):
            pipeline.answer_question(
                "How about Hosted API scenario?",
                user_id="user-a",
                thread_id="thread-a",
                memory_runtime=runtime,
            )

        retrieval_query = retrieve.call_args.args[0]
        self.assertIn("How does the organization recognize revenue?", retrieval_query)
        self.assertIn("How about Hosted API scenario?", retrieval_query)

    def test_runtime_builds_standalone_retrieval_query(self) -> None:
        runtime = _runtime()
        _run_answer("How does the organization recognize revenue?", runtime, "user-a", "thread-a")

        query = runtime.build_retrieval_query("thread-a", "How about Hosted API scenario?")

        self.assertEqual(
            query,
            "How does the organization recognize revenue?\nHow about Hosted API scenario?",
        )

    def test_repeated_question_is_not_added_twice_to_retrieval_query(self) -> None:
        runtime = _runtime()
        _run_answer("How does the organization recognize revenue?", runtime, "user-a", "thread-a")

        query = runtime.build_retrieval_query(
            "thread-a", "How does the organization recognize revenue?"
        )

        self.assertEqual(query, "How does the organization recognize revenue?")

    def test_memory_lifecycle_wraps_enterprise_qa_flow(self) -> None:
        events = []
        runtime = MagicMock()
        runtime.prepare_context.side_effect = lambda **kwargs: (
            events.append("prepare")
            or MemoryContext(
                retrieval_query=kwargs["question"],
                conversation_messages=[],
                long_term_memories=[],
            )
        )
        runtime.record_turn.side_effect = lambda **kwargs: events.append("record")

        with patch.object(
            pipeline.retrieval,
            "retrieve",
            side_effect=lambda *args, **kwargs: (events.append("retrieve") or [_chunk()]),
        ), patch.object(pipeline.retrieval, "is_confident", return_value=True), patch.object(
            pipeline.config, "is_reflection_enabled", return_value=False
        ), patch.object(
            pipeline.llm_client,
            "generate",
            side_effect=lambda *args, **kwargs: (events.append("llm") or "答案"),
        ):
            result = pipeline.answer_question(
                "问题",
                user_id="user-a",
                thread_id="thread-a",
                memory_runtime=runtime,
            )

        self.assertEqual(result.answer, "答案")
        self.assertEqual(events, ["prepare", "retrieve", "llm", "record"])

    def test_same_user_cross_thread_memory_is_semantically_retrieved(self) -> None:
        runtime = _runtime()
        save_user_memory(
            runtime.store,
            "user-a",
            "用户喜欢安静的餐厅。",
            thread_id="thread-a",
        )

        answer = _run_answer("以后回答能不能简单一点？", runtime, "user-a", "thread-b")

        self.assertIn("用户喜欢安静的餐厅。", answer)
        self.assertIn("USER MEMORY:", answer)

    def test_memory_is_isolated_by_user_id(self) -> None:
        runtime = _runtime()
        save_user_memory(runtime.store, "user-a", "用户主要使用 Python。")

        answer = _run_answer("我主要使用什么？", runtime, "user-b", "thread-b")

        self.assertNotIn("用户主要使用 Python。", answer)

    def test_memory_retrieval_failure_does_not_break_qa(self) -> None:
        runtime = _runtime()
        with patch("langchain_memory.app.runtime.retrieve_user_memories", side_effect=RuntimeError("store unavailable")):
            answer = _run_answer("普通问题", runtime, "user-a", "thread-a")

        self.assertIn("ENTERPRISE KNOWLEDGE:", answer)

    def test_memory_write_failure_does_not_break_qa(self) -> None:
        runtime = _runtime()
        extraction = ExtractionModel(
            MemoryExtraction(should_store=True, memory="用户喜欢简洁回答。")
        )
        with patch("langchain_memory.app.config.get_chat_model", return_value=extraction), patch.object(
            pipeline.retrieval, "retrieve", return_value=[_chunk()]
        ), patch.object(pipeline.retrieval, "is_confident", return_value=True), patch.object(
            pipeline.config, "is_reflection_enabled", return_value=False
        ), patch.object(pipeline.llm_client, "generate", return_value="正常答案"):
            runtime.store = FailingWriteStore()
            result = pipeline.answer_question(
                "我喜欢简洁回答。",
                user_id="user-a",
                thread_id="thread-a",
                memory_runtime=runtime,
            )

        self.assertEqual(result.answer, "正常答案")

    def test_default_store_is_configured_with_memory_embeddings(self) -> None:
        embedder = KeywordBagEmbeddings()
        with patch("langchain_memory.app.memory.get_embeddings", return_value=embedder) as factory:
            create_memory_store()

        factory.assert_called_once_with()

    def test_api_identity_headers_reach_pipeline(self) -> None:
        with patch("chat_service.api.routes_ask.answer_question") as answer_question:
            answer_question.return_value.answer = "答案"
            answer_question.return_value.sources = []
            answer_question.return_value.passed_reflection = None
            answer_question.return_value.trace = {}

            ask(
                AskRequest(question="问题"),
                user_id="user_123",
                conversation_id="conv_456",
            )

        answer_question.assert_called_once_with(
            "问题",
            user_id="user_123",
            thread_id="conv_456",
        )
