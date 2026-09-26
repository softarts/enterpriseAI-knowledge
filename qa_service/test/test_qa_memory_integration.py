from __future__ import annotations

from typing import Any
import unittest
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import MemorySaver

from langchain_memory.app.memory import create_memory_store, save_user_memory
from langchain_memory.app.prompts import MemoryExtraction
from langchain_memory.app.runtime import create_memory_runtime
from langchain_memory import MemoryContext
from langchain_memory.tests.test_helpers import DeterministicMockChatModel, KeywordBagEmbeddings
from chat_service.api.routes_ask import ask
from chat_service.services.qa.models import AskRequest
from qa_service import pipeline
from qa_service.models import RetrievedChunk


def _always_search_memory(messages: Any) -> Any:
    """Deterministic retrieval-agent stub: always call search_memory with the
    latest human message as query, mirroring an LLM that decides to search
    whenever the question could depend on user history."""
    last_human = next(
        (m for m in reversed(messages) if getattr(m, "type", "") == "human"),
        None,
    )
    query = str(getattr(last_human, "content", "")) if last_human else ""
    return {"name": "search_memory", "args": {"query": query}}


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
    runtime = create_memory_runtime(store=store, checkpointer=MemorySaver())
    runtime.test_llm = DeterministicMockChatModel(
        response_generator=lambda messages: "\n".join(
            str(getattr(message, "content", ""))
            for message in messages
            if getattr(message, "type", "") in {"system", "tool"}
        ),
        tool_call_rule=_always_search_memory,
    )
    return runtime



        ), patch.object(pipeline.config, "is_reflection_enabled", return_value=True), patch.object(
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
    ), patch.object(
        pipeline.llm_client, "get_llm", return_value=runtime.test_llm
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

    def test_follow_up_question_is_not_naively_concatenated_for_retrieval(self) -> None:
        """Enterprise KB retrieval now always uses the raw current question;
        no more string-heuristic query rewriting based on prior turns."""
        runtime = _runtime()
        _run_answer("How does the organization recognize revenue?", runtime, "user-a", "thread-a")

        with patch.object(pipeline.retrieval, "retrieve", return_value=[_chunk()]) as retrieve, patch.object(
            pipeline.retrieval, "is_confident", return_value=True
        ), patch.object(pipeline.config, "is_reflection_enabled", return_value=False), patch.object(
            pipeline.llm_client, "generate", return_value="正常答案"
        ), patch.object(
            pipeline.llm_client, "get_llm", return_value=runtime.test_llm
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
        self.assertEqual(retrieval_query, "How about Hosted API scenario?")
        self.assertNotIn("How does the organization recognize revenue?", retrieval_query)

    def test_memory_lifecycle_wraps_enterprise_qa_flow(self) -> None:
        events = []
        runtime = MagicMock()
        runtime.prepare_context.side_effect = lambda **kwargs: (
            events.append("prepare")
            or MemoryContext(
                retrieval_query=kwargs["question"],
                conversation_messages=[],
            )
        )
        runtime.record_turn.side_effect = lambda **kwargs: events.append("record")
        runtime.generate_answer_with_memory.side_effect = (
            lambda **kwargs: events.append("llm") or "答案"
        )

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
        ), patch.object(
            pipeline.llm_client,
            "get_llm",
            return_value=DeterministicMockChatModel(),
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
        self.assertNotIn("USER MEMORY:", answer)

    def test_memory_is_isolated_by_user_id(self) -> None:
        runtime = _runtime()
        save_user_memory(runtime.store, "user-a", "用户主要使用 Python。")

        answer = _run_answer("我主要使用什么？", runtime, "user-b", "thread-b")

        self.assertNotIn("用户主要使用 Python。", answer)

    def test_memory_retrieval_failure_does_not_break_qa(self) -> None:
        runtime = _runtime()
        # retrieve_user_memories is now only called from inside the
        # search_memory tool (app/memory.py), not directly from runtime.py.
        with patch("langchain_memory.app.memory.retrieve_user_memories", side_effect=RuntimeError("store unavailable")):
            answer = _run_answer("普通问题", runtime, "user-a", "thread-a")

        self.assertIn("ENTERPRISE KNOWLEDGE:", answer)

    def test_memory_write_failure_does_not_break_qa(self) -> None:
        runtime = _runtime()
        runtime.test_llm.response_generator = lambda messages: "正常答案"
        extraction = ExtractionModel(
            MemoryExtraction(should_store=True, memory="用户喜欢简洁回答。")
        )
        with patch("langchain_memory.app.config.get_chat_model", return_value=extraction), patch.object(
            pipeline.llm_client, "get_llm", return_value=runtime.test_llm
        ), patch.object(
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
