"""SSE stream protocol tests for POST /api/chat/stream.

Covers the mapper (custom + messages channels) and the streaming service
without a live LLM:

    1. custom token payloads become token events
    2. custom tool-call payloads become tool_call events
    3. tool results and usage are derived from the final state
    4. interrupt payloads are synthesized from __interrupt__
    5. token_scope="final" buffers the first round unless a tool call follows
    6. empty question yields error + done
    7. SSE frame framing
    8. end-to-end stream over a scripted LLM
"""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any, List, Optional
from unittest.mock import patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import Field

from chat_service.services.chat.chat_stream import ChatStreamService
from chat_service.services.chat.stream_events import (
    TOKEN_SCOPE_ALL,
    TOKEN_SCOPE_FINAL,
    StreamEventMapper,
)
from langchain_agent.app.runtime import MemoryRuntime


class ScriptedLLM(BaseChatModel):
    """Streams scripted chunks: optional tool call, then text tokens.

    ``_astream`` must yield ``AIMessageChunk`` (not ``ChatGenerationChunk``);
    ``BaseChatModel.astream`` wraps them into generations itself.
    """

    chunks: List[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-llm"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        for item in self.chunks:
            if isinstance(item, str):
                yield ChatGenerationChunk(message=AIMessageChunk(content=item))
            else:
                yield item

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        for item in self.chunks:
            if isinstance(item, str):
                yield AIMessageChunk(content=item)
            else:
                yield item

    def bind_tools(self, tools, **kwargs):
        parent = self

        class _Bound:
            def invoke(self, messages, config=None, **kw):
                return parent._generate(messages).generations[0].message

            def stream(self, messages, config=None, **kw):
                return parent._stream(messages)

            async def astream(self, messages, config=None, **kw):
                async for chunk in parent._astream(messages):
                    yield chunk

        return _Bound()

    def with_structured_output(self, schema, **kwargs):
        class _Structured:
            def invoke(self, messages, config=None, **kw):
                from types import SimpleNamespace

                return SimpleNamespace(should_store=False, memory="")

        return _Structured()


def _tool_call_chunk(name: str, call_id: str, args: dict) -> Any:
    """Build a streamed tool-call fragment as an AIMessageChunk.

    langchain-core 1.x requires ``tool_call_chunks[].args`` to be a JSON string
    fragment (the parser reassembles it), not a dict.
    """
    return AIMessageChunk(
        content="",
        tool_call_chunks=[
            {
                "name": name,
                "args": json.dumps(args, ensure_ascii=False),
                "id": call_id,
                "index": 0,
                "type": "tool_call_chunk",
            }
        ],
    )


class StreamEventMapperTest(unittest.TestCase):
    def test_custom_token_becomes_token_event(self) -> None:
        mapper = StreamEventMapper(thread_id="t1")
        events = mapper.map_custom({"kind": "token", "text": "你"})
        self.assertEqual([e.type for e in events], ["token"])
        self.assertEqual(events[0].data["text"], "你")

    def test_empty_custom_token_ignored(self) -> None:
        mapper = StreamEventMapper(thread_id="t1")
        self.assertEqual(mapper.map_custom({"kind": "token", "text": ""}), [])

    def test_custom_tool_call_becomes_tool_call_event(self) -> None:
        mapper = StreamEventMapper(thread_id="t1")
        events = mapper.map_custom(
            {"kind": "tool_call", "id": "c1", "name": "web_search", "args": {"query": "q"}}
        )
        self.assertEqual([e.type for e in events], ["tool_call"])
        self.assertEqual(events[0].data["id"], "c1")
        self.assertEqual(events[0].data["name"], "web_search")
        self.assertEqual(events[0].data["args"], {"query": "q"})

    def test_interrupt_synthesized(self) -> None:
        mapper = StreamEventMapper(thread_id="conv-1")
        interrupt_obj = type("Interrupt", (), {})()
        interrupt_obj.value = {
            "question": "即将调用外部工具 web_search，是否继续？",
            "tools": [{"id": "c1", "name": "web_search", "args": {}}],
        }
        # A paused run reports a top-level __interrupt__ key on the updates channel.
        events = mapper.map_updates({"__interrupt__": [interrupt_obj]})
        self.assertEqual([e.type for e in events], ["interrupt"])
        interrupt = events[0]
        self.assertEqual(interrupt.data["thread_id"], "conv-1")
        self.assertEqual(interrupt.data["resume_key"], "conv-1:c1")
        self.assertIn("web_search", interrupt.data["question"])

    def test_node_start_from_messages_tuple(self) -> None:
        mapper = StreamEventMapper(thread_id="t1")
        first = mapper.map_messages((AIMessage(content="hi"), {"langgraph_node": "agent"}))
        second = mapper.map_messages((AIMessage(content="hi"), {"langgraph_node": "agent"}))
        self.assertEqual([e.type for e in first], ["node_start"])
        self.assertEqual(first[0].data["node"], "agent")
        self.assertEqual(second, [], "repeat node messages must not re-emit node_start")

    def test_node_start_from_updates(self) -> None:
        mapper = StreamEventMapper(thread_id="t1")
        events = mapper.map_updates({"agent": {"messages": []}})
        self.assertEqual([e.type for e in events], ["node_start"])
        self.assertEqual(events[0].data["node"], "agent")

    def test_token_scope_all_streams_immediately(self) -> None:
        mapper = StreamEventMapper(thread_id="t1", token_scope=TOKEN_SCOPE_ALL)
        events = mapper.map_custom({"kind": "token", "text": "立即"})
        self.assertEqual(events[0].type, "token")
        self.assertEqual(mapper.flush_final_scope(), [])

    def test_token_scope_final_buffers_until_flushed(self) -> None:
        mapper = StreamEventMapper(thread_id="t1", token_scope=TOKEN_SCOPE_FINAL)
        self.assertEqual(mapper.map_custom({"kind": "token", "text": "答案"}), [])
        flushed = mapper.flush_final_scope()
        self.assertEqual([e.type for e in flushed], ["token"])
        self.assertEqual(flushed[0].data["text"], "答案")

    def test_token_scope_final_streams_after_tool_call(self) -> None:
        """Once a tool ran, the next round is the final answer and streams now."""
        mapper = StreamEventMapper(thread_id="t1", token_scope=TOKEN_SCOPE_FINAL)
        mapper.map_custom({"kind": "tool_call", "id": "c1", "name": "calc", "args": {}})
        events = mapper.map_custom({"kind": "token", "text": "最终答案"})
        self.assertEqual([e.type for e in events], ["token"])
        self.assertEqual(events[0].data["text"], "最终答案")

    def test_usage_accumulates(self) -> None:
        mapper = StreamEventMapper(thread_id="t1")
        mapper.usage.add({"input_tokens": 100, "output_tokens": 5})
        mapper.usage.add({"prompt_tokens": 20, "completion_tokens": 7})
        self.assertEqual(
            mapper.usage.to_dict(), {"input_tokens": 120, "output_tokens": 12}
        )


class ChatStreamServiceTest(unittest.TestCase):
    def _service(self) -> ChatStreamService:
        return ChatStreamService(
            memory_runtime=MemoryRuntime(
                checkpointer=InMemorySaver(), store=InMemoryStore()
            )
        )

    def test_empty_question_emits_error_and_done(self) -> None:
        service = self._service()

        async def collect():
            return [
                event
                async for event in service.stream_turn(question="   ", thread_id="t1")
            ]

        events = asyncio.run(collect())
        self.assertEqual([e.type for e in events], ["error", "done"])
        self.assertEqual(events[1].data["finish_reason"], "stop")

    def test_sse_frame_format(self) -> None:
        service = self._service()

        async def collect():
            return [
                event.to_sse()
                async for event in service.stream_turn(question="", thread_id="t1")
            ]

        frames = asyncio.run(collect())
        self.assertTrue(frames[0].startswith("data: "))
        self.assertTrue(frames[0].endswith("\n\n"))
        payload = json.loads(frames[0][len("data: ") : -2])
        self.assertEqual(payload["type"], "error")

    def test_end_to_end_tokens_and_done(self) -> None:
        service = self._service()
        llm = ScriptedLLM(chunks=["你好", "世界"])

        async def collect():
            return [
                event
                async for event in service.stream_turn(
                    question="你好", thread_id="t-e2e", llm=llm
                )
            ]

        events = asyncio.run(collect())
        types = [e.type for e in events]
        self.assertEqual(types[-1], "done")
        tokens = "".join(e.data["text"] for e in events if e.type == "token")
        self.assertEqual(tokens, "你好世界")
        self.assertIn("node_start", types)

    def test_end_to_end_tool_call_and_result(self) -> None:
        service = self._service()
        llm = ScriptedLLM(
            chunks=[
                _tool_call_chunk("get_current_time", "c1", {}),
                "现在时间已获取",
            ]
        )

        async def collect():
            return [
                event
                async for event in service.stream_turn(
                    question="现在几点", thread_id="t-tool", llm=llm
                )
            ]

        with patch(
            "chat_service.services.chat.chat_stream.RECURSION_LIMIT", 25
        ):
            events = asyncio.run(collect())

        types = [e.type for e in events]
        self.assertIn("tool_call", types)
        self.assertIn("tool_result", types)
        self.assertEqual(types[-1], "done")
        call = next(e for e in events if e.type == "tool_call")
        self.assertEqual(call.data["name"], "get_current_time")
        result = next(e for e in events if e.type == "tool_result")
        self.assertEqual(result.data["id"], "c1")
        self.assertEqual(result.data["name"], "get_current_time")
        self.assertIn("2026", result.data["content"])


if __name__ == "__main__":
    unittest.main()
