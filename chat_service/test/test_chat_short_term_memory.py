from __future__ import annotations

from typing import Any, Dict
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from chat_service.api import routes_chat
from chat_service.services.chat.chat_service import ChatService
from langchain_core.messages import BaseMessage
from langchain_agent.app.runtime import MemoryRuntime
from langchain_agent.tests.test_helpers import DeterministicMockChatModel


class RecordingMemoryRuntime:
    def __init__(self) -> None:
        self.call: Dict[str, Any] = {}

    def generate_answer_with_memory(self, **kwargs: Any) -> str:
        self.call = kwargs
        return "带有 thread 上下文的回答"

    def prepare_context(self, **kwargs: Any) -> Any:
        return type("MemoryContext", (), {"conversation_messages": []})()


class TestChatShortTermMemory(unittest.TestCase):
    def test_chat_service_uses_shared_llm_and_thread_id(self) -> None:
        runtime = RecordingMemoryRuntime()
        service = ChatService(memory_runtime=runtime)
        llm = object()
        with patch("chat_service.services.chat.chat_service.llm_client.get_llm", return_value=llm), patch(
            "chat_service.services.chat.chat_service.llm_client.get_model_config",
            return_value={"model": "test-model", "max_tokens": 50},
        ):
            result = service.ask("你好", thread_id="conversation-1")

        self.assertEqual(result.answer, "带有 thread 上下文的回答")
        self.assertIs(runtime.call["llm"], llm)
        self.assertEqual(runtime.call["thread_id"], "conversation-1")
        self.assertEqual(runtime.call["question"], "你好")

    def test_each_trace_reports_checkpoint_history_for_its_request(self) -> None:
        checkpointer = MemorySaver()
        runtime = MemoryRuntime(checkpointer=checkpointer)

        def answer_from_history(messages: list[BaseMessage]) -> str:
            all_content = " ".join(str(message.content) for message in messages)
            if "老周" in all_content and "我是谁" in str(messages[-1].content):
                return "你刚才告诉我你是老周。"
            return "你好，老周。"

        llm = DeterministicMockChatModel(response_generator=answer_from_history)
        service = ChatService(memory_runtime=runtime)
        with patch(
            "chat_service.services.chat.chat_service.llm_client.get_llm",
            return_value=llm,
        ), patch(
            "chat_service.services.chat.chat_service.llm_client.get_model_config",
            return_value={"model": "test-model", "max_tokens": 50},
        ):
            first_result = service.ask("我是老周，你是谁", thread_id="conversation-1")
            second_result = service.ask("我是谁", thread_id="conversation-1")

        self.assertEqual(first_result.trace["request"]["checkpoint_messages_before"], 0)
        self.assertEqual(second_result.trace["request"]["checkpoint_messages_before"], 2)
        self.assertEqual(second_result.trace["request"]["question"], "我是谁")
        self.assertEqual(
            second_result.trace["response"]["answer"],
            "你刚才告诉我你是老周。",
        )
        self.assertNotEqual(first_result.trace["trace_id"], second_result.trace["trace_id"])
        # The per-LLM-call payload now comes from call_trace's callback handler
        # (kind="llm"), not from a node-local "agent" span: the graph nodes no
        # longer record their own span, so one entry appears per LLM call the
        # model made. This turn has no tool calls, so exactly one is expected.
        # "llm" remains the pre-existing aggregate step.
        step_names = [step["name"] for step in second_result.trace["steps"]]
        self.assertEqual(step_names.count("llm_call"), 1)
        self.assertNotIn("agent", step_names)
        llm_steps = [
            step for step in second_result.trace["steps"] if step["name"] == "llm_call"
        ]
        self.assertEqual(llm_steps[0]["kind"], "llm")
        # The aggregated response is captured from on_llm_end, not rebuilt by
        # the node — so it carries the real answer text.
        response = llm_steps[0]["detail"]["response"]
        self.assertEqual(response["content"], "你刚才告诉我你是老周。")
        self.assertIn("老周", second_result.answer)

    def test_api_requires_and_forwards_conversation_header(self) -> None:
        app = FastAPI()
        app.include_router(routes_chat.router)
        original_service = routes_chat._chat_service
        routes_chat._chat_service = ChatService(memory_runtime=RecordingMemoryRuntime())
        client = TestClient(app)
        try:
            with patch(
                "chat_service.services.chat.chat_service.llm_client.get_llm",
                return_value=object(),
            ), patch(
                "chat_service.services.chat.chat_service.llm_client.get_model_config",
                return_value={"model": "test-model", "max_tokens": 50},
            ):
                missing_header = client.post("/api/chat", json={"question": "你好"})
                self.assertEqual(missing_header.status_code, 422)

                response = client.post(
                    "/api/chat",
                    json={"question": "你好"},
                    headers={"X-Conversation-Id": "conversation-1"},
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["answer"], "带有 thread 上下文的回答")
            self.assertIn("trace", response.json())
            self.assertIsNone(response.json()["error"])
        finally:
            routes_chat._chat_service = original_service
            client.close()

    def test_empty_question_does_not_call_llm(self) -> None:
        runtime = RecordingMemoryRuntime()
        service = ChatService(memory_runtime=runtime)
        with patch("chat_service.services.chat.chat_service.llm_client.get_llm") as get_llm:
            result = service.ask("  ", thread_id="conversation-1")

        self.assertEqual(result.error, "Question must not be empty.")
        get_llm.assert_not_called()
        self.assertEqual(runtime.call, {})


if __name__ == "__main__":
    unittest.main()
