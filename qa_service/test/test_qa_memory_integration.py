from __future__ import annotations

from typing import Any, List
import unittest
from unittest.mock import patch

from langchain_core.messages import BaseMessage
from langgraph.checkpoint.memory import MemorySaver

from langchain_memory.app.runtime import create_memory_runtime
from langchain_memory.tests.test_helpers import DeterministicMockChatModel
from chat_service.api.routes_ask import ask
from chat_service.services.qa.models import AskRequest
from qa_service import pipeline
from qa_service.models import RetrievedChunk


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


def _run_answer(question: str, runtime: Any, thread_id: str) -> str:
    with patch.object(pipeline.retrieval, "retrieve", return_value=[_chunk()]), patch.object(
        pipeline.retrieval, "is_confident", return_value=True
    ), patch.object(pipeline.config, "is_reflection_enabled", return_value=False), patch.object(
        pipeline.llm_client, "get_llm", return_value=runtime.test_llm
    ):
        return pipeline.answer_question(
            question,
            thread_id=thread_id,
            memory_runtime=runtime,
        ).answer


class TestQAShortTermMemoryIntegration(unittest.TestCase):
    def _create_runtime(self, response_generator: Any) -> Any:
        runtime = create_memory_runtime(checkpointer=MemorySaver())
        runtime.test_llm = DeterministicMockChatModel(response_generator=response_generator)
        return runtime

    def test_answer_agent_restores_history_for_same_thread(self) -> None:
        def answer_from_history(messages: List[BaseMessage]) -> str:
            current_question = str(messages[-1].content)
            combined = " ".join(str(message.content) for message in messages)
            if "Alice" in combined and "叫什么名字" in current_question:
                return "你叫 Alice。"
            return "收到。"

        runtime = self._create_runtime(answer_from_history)
        _run_answer("我的名字是 Alice。", runtime, "thread-a")
        context = runtime.prepare_context(thread_id="thread-a", question="我叫什么名字？")

        answer = _run_answer("我叫什么名字？", runtime, "thread-a")

        self.assertEqual(len(context.conversation_messages), 2)
        self.assertEqual(answer, "你叫 Alice。")

    def test_enterprise_retrieval_uses_only_current_question(self) -> None:
        runtime = self._create_runtime(lambda messages: "答案")
        _run_answer("上一轮问题", runtime, "thread-a")
        with patch.object(pipeline.retrieval, "retrieve", return_value=[_chunk()]) as retrieve, patch.object(
            pipeline.retrieval, "is_confident", return_value=True
        ), patch.object(pipeline.config, "is_reflection_enabled", return_value=False), patch.object(
            pipeline.llm_client, "get_llm", return_value=runtime.test_llm
        ):
            pipeline.answer_question(
                "当前追问",
                thread_id="thread-a",
                memory_runtime=runtime,
            )

        self.assertEqual(retrieve.call_args.args[0], "当前追问")

    def test_threadless_qa_uses_existing_stateless_generation(self) -> None:
        with patch.object(pipeline.retrieval, "retrieve", return_value=[_chunk()]), patch.object(
            pipeline.retrieval, "is_confident", return_value=True
        ), patch.object(pipeline.llm_client, "generate", return_value="无状态答案") as generate:
            result = pipeline.answer_question("问题")

        self.assertEqual(result.answer, "无状态答案")
        generate.assert_called_once()

    def test_api_forwards_conversation_id_as_checkpoint_thread(self) -> None:
        with patch("chat_service.api.routes_ask.answer_question") as answer_question:
            answer_question.return_value.answer = "答案"
            answer_question.return_value.sources = []
            answer_question.return_value.passed_reflection = None
            answer_question.return_value.trace = {}

            ask(
                AskRequest(question="问题"),
                conversation_id="conv-456",
            )

        answer_question.assert_called_once_with("问题", thread_id="conv-456")


if __name__ == "__main__":
    unittest.main()
