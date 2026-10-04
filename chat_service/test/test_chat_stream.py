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
    9. trace events carry the aggregated per-LLM-call payload
"""

from __future__ import annotations

import asyncio
import json
import unittest
import uuid
from decimal import Decimal
from typing import Any, List
from unittest.mock import patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import Field

from chat_service.services.chat.chat_stream import ChatStreamService
from chat_service.services.chat.stream_events import (
    TOKEN_SCOPE_ALL,
    TOKEN_SCOPE_FINAL,
    StreamEvent,
    StreamEventMapper,
)
from langchain_agent.app.runtime import MemoryRuntime


class ScriptedLLM(BaseChatModel):
    """Streams scripted chunks: optional tool call, then text tokens.

    Both ``_stream`` and ``_astream`` yield ``ChatGenerationChunk``, which is
    what ``BaseChatModel.stream``/``astream`` expect from a real provider
    model — it wraps each into the ``AIMessageChunk`` the graph node sees.
    (Handing the graph raw ``AIMessageChunk`` objects only worked while
    ``bind_tools`` returned a bespoke wrapper; with a real RunnableBinding the
    core machinery does that wrapping itself.)
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
                yield ChatGenerationChunk(message=AIMessageChunk(content=item))
            else:
                yield item

    def bind_tools(self, tools, **kwargs):
        # A real RunnableBinding (not a hand-rolled wrapper) so the per-call
        # trace handler's on_chat_model_start / on_llm_end callbacks actually
        # fire; a plain object with an `astream` method bypasses them.
        return self.bind(
            tools=[convert_to_openai_tool(tool) for tool in tools],
            **kwargs,
        )

    def with_structured_output(self, schema, **kwargs):
        class _Structured:
            def invoke(self, messages, config=None, **kw):
                from types import SimpleNamespace

                return SimpleNamespace(should_store=False, memory="")

        return _Structured()


def _tool_call_chunk(name: str, call_id: str, args: dict) -> Any:
    """Build a streamed tool-call fragment as a ChatGenerationChunk.

    langchain-core 1.x requires ``tool_call_chunks[].args`` to be a JSON string
    fragment (the parser reassembles it), not a dict. Yielded as a
    ``ChatGenerationChunk`` because that is what a provider model's
    ``_astream`` returns; ``BaseChatModel.astream`` unwraps it into the
    ``AIMessageChunk`` the graph node consumes.
    """
    return ChatGenerationChunk(
        message=AIMessageChunk(
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

    def test_sse_frame_survives_non_serializable_values(self) -> None:
        """A frame must never raise, whatever ended up in its data.

        Regression: a trace detail carried LangChain's ``run_id`` UUID *object*
        into the SSE payload, and ``json.dumps`` raised inside Starlette's ASGI
        send path — killing the whole response on the first trace frame.
        Anything unserializable is rendered as a string instead.
        """
        event = StreamEvent(
            "trace",
            {
                "kind": "llm",
                "llm_call_id": uuid.UUID("01a10703-4430-70b0-8fd0-d603415de991"),
                "detail": {"elapsed": Decimal("1.5")},
            },
        )
        frame = event.to_sse()
        self.assertTrue(frame.startswith("data: {"))
        # Still valid JSON, and the UUID round-trips as text.
        parsed = json.loads(frame[len("data: ") :])
        self.assertEqual(parsed["type"], "trace")
        self.assertEqual(parsed["llm_call_id"], "01a10703-4430-70b0-8fd0-d603415de991")
        self.assertEqual(parsed["detail"]["elapsed"], "1.5")


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

    def test_tool_row_carries_arguments_and_result(self) -> None:
        """The `tool` row must expose what was asked and what came back.

        Regression: `tool` rows fell through to the generic
        `JSON.stringify(step.detail)` fallback, so the query and the Tavily
        payload were technically present but not rendered as inspectable
        sections.
        """
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
                    question="现在几点", thread_id="t-tool-args", llm=llm
                )
            ]

        with patch("chat_service.services.chat.chat_stream.RECURSION_LIMIT", 25):
            events = asyncio.run(collect())

        tool_rows = [
            e for e in events if e.type == "trace" and e.data["kind"] == "tool"
        ]
        self.assertTrue(tool_rows)
        detail = tool_rows[-1].data["detail"]
        # Arguments the model passed, and the tool's result — both inspectable.
        self.assertIn("arguments", detail)
        self.assertIn("result", detail)
        self.assertTrue(detail["result"])

    def test_llm_call_records_the_tools_it_decided_to_call(self) -> None:
        """The decision to search is on the llm row; execution is the tool row.

        These are two different facts and must not be conflated: the model
        *asking* for web_search lives in the llm call's response.tool_calls,
        while the `tool` row is web_search *running*. The UI relies on this
        split to explain the pairing.
        """
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
                    question="现在几点", thread_id="t-decision", llm=llm
                )
            ]

        with patch("chat_service.services.chat.chat_stream.RECURSION_LIMIT", 25):
            events = asyncio.run(collect())

        llm_rows = [
            e for e in events if e.type == "trace" and e.data["kind"] == "llm"
        ]
        self.assertTrue(llm_rows)
        deciding = [
            row
            for row in llm_rows
            if (row.data["detail"].get("response") or {}).get("tool_calls")
        ]
        self.assertTrue(deciding, "the llm row must record the requested tool call")
        self.assertEqual(
            deciding[0].data["detail"]["response"]["tool_calls"][0]["name"],
            "get_current_time",
        )
        # ...and the tools it was *offered* are on the request side.
        bound = deciding[0].data["detail"]["request"].get("tools_bound") or []
        self.assertIn("get_current_time", [t["name"] for t in bound])

    def test_every_trace_row_carries_the_conversation_id(self) -> None:
        """Each row is self-identifying, so rows stay attributable.

        Several conversations interleave in one log file and one UI timeline;
        without the id on the row you can only attribute a line by matching
        timestamps.
        """
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
                    question="现在几点", thread_id="conversation-abc-123", llm=llm
                )
            ]

        with patch("chat_service.services.chat.chat_stream.RECURSION_LIMIT", 25):
            events = asyncio.run(collect())

        trace_rows = [e for e in events if e.type == "trace"]
        self.assertTrue(trace_rows)
        for row in trace_rows:
            self.assertEqual(
                row.data.get("conversation_id"),
                "conversation-abc-123",
                f"trace row {row.data.get('name')} is missing its conversation id",
            )

    def test_payloads_are_not_truncated(self) -> None:
        """Long payloads must arrive in full.

        The trace is a debugging tool: a silently shortened body is worse than
        a long one, because a clipped payload is indistinguishable from a
        genuinely small one. Only error strings are bounded.
        """
        service = self._service()
        # Well beyond the 4000-char clip that used to be applied here.
        long_answer = "答" * 20000
        llm = ScriptedLLM(chunks=[long_answer])

        async def collect():
            return [
                event
                async for event in service.stream_turn(
                    question="长回答", thread_id="t-long", llm=llm
                )
            ]

        with patch("chat_service.services.chat.chat_stream.RECURSION_LIMIT", 25):
            events = asyncio.run(collect())

        llm_rows = [
            e for e in events if e.type == "trace" and e.data["kind"] == "llm"
        ]
        self.assertTrue(llm_rows)
        content = llm_rows[-1].data["detail"]["response"]["content"]
        self.assertEqual(len(content), len(long_answer))
        self.assertNotIn("truncated", content)
        # And it must still survive SSE serialization.
        frame = llm_rows[-1].to_sse()
        self.assertEqual(len(json.loads(frame[len("data: ") :])["detail"]["response"]["content"]), 20000)

    def test_trace_reports_one_aggregated_entry_per_llm_call(self) -> None:
        """One `kind="llm"` row per LLM call, carrying the merged response.

        The row is emitted twice — provisionally while the call is in flight
        and again once finalized — under the *same* `seq`, so the client
        replaces it instead of appending a duplicate.
        """
        service = self._service()
        llm = ScriptedLLM(chunks=["你", "好", "世界"])

        async def collect():
            return [
                event
                async for event in service.stream_turn(
                    question="打招呼", thread_id="t-trace", llm=llm
                )
            ]

        with patch("chat_service.services.chat.chat_stream.RECURSION_LIMIT", 25):
            events = asyncio.run(collect())

        traces = [e for e in events if e.type == "trace"]
        llm_rows = [t for t in traces if t.data["kind"] == "llm"]
        self.assertTrue(llm_rows, "expected at least one kind='llm' trace row")

        # Every row for this call shares one seq, so they collapse to a single
        # row in the UI.
        seqs = {t.data["seq"] for t in llm_rows}
        self.assertEqual(len(seqs), 1, "one LLM call must map to one stable seq")

        final = llm_rows[-1]
        self.assertEqual(final.data["status"], "ok")
        self.assertIsNotNone(final.data["duration_ms"])
        # The *aggregated* answer, not a single token — this is the whole point
        # of moving off per-chunk/per-node recording.
        self.assertEqual(
            final.data["detail"]["response"]["content"], "你好世界"
        )
        # Which graph node issued the call is preserved (it used to come from
        # a separate `record_local("agent", ...)` span).
        self.assertEqual(final.data["detail"]["request"]["node"], "agent")
        # Stable identity for correlating with the httpx attempts underneath.
        self.assertTrue(final.data["llm_call_id"])

    def test_trace_marks_tool_executions_as_tool_kind(self) -> None:
        """Executed tools surface as `kind="tool"`, with args and result.

        This is the layer that sees `web_search`, whose Tavily traffic goes
        through requests/aiohttp and therefore never appears in the httpx
        hooks at all.
        """
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
                    question="现在几点", thread_id="t-tool-trace", llm=llm
                )
            ]

        with patch("chat_service.services.chat.chat_stream.RECURSION_LIMIT", 25):
            events = asyncio.run(collect())

        tool_rows = [
            t for t in events if t.type == "trace" and t.data["kind"] == "tool"
        ]
        self.assertTrue(tool_rows, "expected a kind='tool' trace row")
        row = tool_rows[-1]
        self.assertEqual(row.data["name"], "get_current_time")
        self.assertEqual(row.data["status"], "ok")
        self.assertEqual(row.data["tool_call_id"], "c1")
        self.assertIn("2026", row.data["detail"]["result"])
        self.assertIsNotNone(row.data["duration_ms"])

    def test_identifiers_are_strings_so_frames_stay_serializable(self) -> None:
        """``llm_call_id``/``tool_call_id`` must be text, not UUID objects.

        Regression: LangChain hands callbacks a ``run_id`` UUID *instance*.
        Passing it through into the event data made ``json.dumps`` raise
        ``TypeError: Object of type UUID is not JSON serializable`` inside the
        SSE send path, which aborted the response on the very first trace
        frame. Assert the rendered frame, not just the field, so the whole
        path is covered.
        """
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
                    question="现在几点", thread_id="t-ids", llm=llm
                )
            ]

        with patch("chat_service.services.chat.chat_stream.RECURSION_LIMIT", 25):
            events = asyncio.run(collect())

        # Every frame must serialize; this is what the ASGI send path does.
        for event in events:
            frame = event.to_sse()
            self.assertTrue(frame.endswith("\n\n"))
            json.loads(frame[len("data: ") :])

        llm_rows = [
            e for e in events if e.type == "trace" and e.data["kind"] == "llm"
        ]
        self.assertTrue(llm_rows)
        self.assertIsInstance(llm_rows[-1].data["llm_call_id"], str)

        tool_rows = [
            e for e in events if e.type == "trace" and e.data["kind"] == "tool"
        ]
        self.assertTrue(tool_rows)
        self.assertIsInstance(tool_rows[-1].data["tool_call_id"], str)

    def test_abandoned_stream_does_not_raise_on_scope_teardown(self) -> None:
        """A stream abandoned mid-flight must tear down without raising.

        Regression: the SSE body iterator is a generator suspended across a
        ``yield``, so when the client disconnects Starlette finalizes it from
        a different task. ``ContextVar.reset`` then fails with
        ``ValueError: ... was created in a different Context``.

        Driven against ``_run`` (not the ``stream_turn`` wrapper, which adds a
        second generator layer and absorbs the error) on a live loop:
        ``asyncio.run`` cancels a still-pending generator during loop
        shutdown, finalizing it in-place so no Context boundary is ever
        crossed and the bug would slip through.
        """
        service = self._service()
        llm = ScriptedLLM(chunks=["你", "好", "世界"])
        failures: List[str] = []

        async def scenario():
            graph = service._build_graph(llm=llm)
            config = service._build_config("t-abandon", None)
            agen = service._run(
                graph,
                {"messages": [HumanMessage(content="打招呼")]},
                config,
                "t-abandon",
                TOKEN_SCOPE_ALL,
            )
            frames = 0
            async for _ in agen:
                frames += 1
                if frames == 1:
                    break  # client "disconnects" mid-stream

            # Finalize from a *different* task, the way Starlette's task
            # group does once the response is torn down.
            task = asyncio.create_task(agen.aclose())
            try:
                await task
            except BaseException as exc:  # noqa: BLE001
                failures.append(f"{type(exc).__name__}: {exc}")
            return frames

        async def main():
            with patch("chat_service.services.chat.chat_stream.RECURSION_LIMIT", 25):
                return await scenario()

        frames = asyncio.run(main())
        self.assertGreaterEqual(frames, 1)
        self.assertEqual(
            failures,
            [],
            "closing the stream from another task must not raise "
            "(a ContextVar reset cannot succeed there)",
        )


if __name__ == "__main__":
    unittest.main()
