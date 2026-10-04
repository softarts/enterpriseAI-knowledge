from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import patch

_module_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _module_dir not in sys.path:
    sys.path.insert(0, _module_dir)

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.store.memory import InMemoryStore

from app.graph import build_memory_agent_graph
from app.runtime import (
    GRAPH_RECURSION_LIMIT,
    RECURSION_LIMIT_ANSWER,
    MemoryRuntime,
)
from app.tool_layer import (
    calculator,
    create_web_search_tool,
    get_current_time,
)


class ScriptedChatModel:
    """Deterministic tool-call script for exercising the real LangGraph loop."""

    def __init__(self, actions: List[Dict[str, Any]]) -> None:
        self.actions = list(actions)
        self.available_tools = set()
        self.inputs: List[List[Any]] = []

    def bind_tools(self, tools: List[Any]) -> "ScriptedChatModel":
        self.available_tools = {tool.name for tool in tools}
        return self

    def invoke(self, messages: List[Any], config: Any = None) -> AIMessage:
        self.inputs.append(list(messages))
        if not self.actions:
            raise AssertionError("The model script ran out of actions")
        action = self.actions.pop(0)
        if action["kind"] == "tool":
            self.assert_tool_available(action["name"])
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": action["name"],
                        "args": action.get("args", {}),
                        "id": f"call_{len(self.inputs)}",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content=action["content"])

    def assert_tool_available(self, name: str) -> None:
        if name not in self.available_tools:
            raise AssertionError(f"Model requested unavailable tool: {name}")

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        class StructuredOutput:
            def invoke(self, messages: Any, config: Any = None) -> Any:
                return schema(should_store=False, memory=None)

        return StructuredOutput()


class FakeSearchTool:
    def __init__(self, response: Dict[str, Any], error: Exception = None) -> None:
        self.response = response
        self.error = error
        self.calls: List[Dict[str, Any]] = []

    def invoke(self, args: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append(args)
        if self.error:
            raise self.error
        return self.response


def _tool_action(name: str, args: Dict[str, Any] = None) -> Dict[str, Any]:
    return {"kind": "tool", "name": name, "args": args or {}}


def _final_action(content: str = "Done.") -> Dict[str, Any]:
    return {"kind": "final", "content": content}


def _run_case(
    actions: List[Dict[str, Any]],
    question: str,
    search_response: Dict[str, Any] = None,
):
    fake_search = FakeSearchTool(search_response or {"results": []})
    tools = [
        create_web_search_tool(search_tool=fake_search),
        calculator,
        get_current_time,
    ]
    model = ScriptedChatModel(actions)
    with patch("app.graph.app_config.HITL_ENABLED", False):
        graph = build_memory_agent_graph(
            llm=model,
            checkpointer=MemorySaver(),
            store=InMemoryStore(),
            tools=tools,
        )
        result = graph.invoke(
            {"messages": [HumanMessage(content=question)]},
            config={"configurable": {"thread_id": "tool-layer-test"}},
        )
    observations = [
        message for message in result["messages"] if isinstance(message, ToolMessage)
    ]
    return result, model, fake_search, observations


class TestToolImplementations(unittest.TestCase):
    def test_calculator_accepts_arithmetic_and_rejects_code(self) -> None:
        self.assertEqual(calculator.invoke({"expression": "2**30"}), "1073741824")
        division_error = calculator.invoke({"expression": "1 / 0"})
        self.assertEqual(
            division_error,
            "Tool failed: division by zero is not allowed. Try a different approach.",
        )
        code_error = calculator.invoke(
            {"expression": "__import__('os').system('echo unsafe')"}
        )
        self.assertTrue(code_error.startswith("Tool failed: "))
        self.assertIn("Try a different approach.", code_error)

    def test_time_is_iso_8601_with_timezone(self) -> None:
        timestamp = get_current_time.invoke({})
        parsed = datetime.fromisoformat(timestamp)
        self.assertIsNotNone(parsed.tzinfo)

    def test_web_search_truncates_output_and_standardizes_failures(self) -> None:
        long_search = create_web_search_tool(
            search_tool=FakeSearchTool(
                {
                    "results": [
                        {"title": "News", "content": "x" * 2500, "url": "https://example.com"}
                    ]
                }
            )
        )
        output = long_search.invoke({"query": "recent news"})
        self.assertLessEqual(len(output), 2000)
        self.assertTrue(output.endswith("...[truncated]"))

        failed_search = create_web_search_tool(
            search_tool=FakeSearchTool({}, error=RuntimeError("upstream down"))
        )
        failure = failed_search.invoke({"query": "recent news"})
        self.assertTrue(failure.startswith("Tool failed: "))
        self.assertTrue(failure.endswith("Try a different approach."))

    def test_missing_tavily_package_is_a_tool_observation(self) -> None:
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}), patch.dict(
            sys.modules, {"langchain_tavily": None}
        ):
            result = create_web_search_tool().invoke({"query": "recent news"})

        self.assertTrue(result.startswith("Tool failed: "))
        self.assertIn("ModuleNotFoundError", result)
        self.assertTrue(result.endswith("Try a different approach."))


class TestReActToolSequences(unittest.TestCase):
    def test_current_time_uses_only_time_tool(self) -> None:
        _, _, _, observations = _run_case(
            [_tool_action("get_current_time"), _final_action("UTC time returned.")],
            "现在几点？",
        )
        self.assertEqual([message.name for message in observations], ["get_current_time"])

    def test_power_uses_only_calculator(self) -> None:
        _, _, _, observations = _run_case(
            [
                _tool_action("calculator", {"expression": "2**30"}),
                _final_action("2 的 30 次方是 1073741824。"),
            ],
            "2 的 30 次方是多少？",
        )
        self.assertEqual([message.name for message in observations], ["calculator"])
        self.assertEqual(observations[0].content, "1073741824")

    def test_current_news_uses_only_web_search(self) -> None:
        search_response = {
            "results": [
                {
                    "title": "OpenAI news",
                    "content": "A current announcement.",
                    "url": "https://example.com/openai",
                }
            ]
        }
        _, _, fake_search, observations = _run_case(
            [
                _tool_action("web_search", {"query": "OpenAI news today"}),
                _final_action("Here is today's news."),
            ],
            "今天 OpenAI 有什么新闻？",
            search_response,
        )
        self.assertEqual([message.name for message in observations], ["web_search"])
        self.assertIn("https://example.com/openai", observations[0].content)
        self.assertEqual(fake_search.calls, [{"query": "OpenAI news today"}])

    def test_latest_price_then_calculation_runs_two_tool_rounds(self) -> None:
        search_response = {
            "results": [
                {
                    "title": "NVDA quote",
                    "content": "Latest price: 120.00 USD.",
                    "url": "https://example.com/nvda",
                }
            ]
        }
        _, model, _, observations = _run_case(
            [
                _tool_action("web_search", {"query": "NVDA latest stock price USD"}),
                _tool_action("calculator", {"expression": "120 * 1.15"}),
                _final_action("At 15% growth, the price would be 138 USD."),
            ],
            "先搜一下 NVDA 的最新股价，再算一下如果涨 15% 是多少。",
            search_response,
        )
        self.assertEqual(
            [message.name for message in observations], ["web_search", "calculator"]
        )
        self.assertEqual(observations[1].content, "138.0")
        self.assertTrue(
            any(
                isinstance(message, ToolMessage) and message.name == "web_search"
                for message in model.inputs[1]
            )
        )
        self.assertTrue(
            any(
                isinstance(message, ToolMessage) and message.name == "calculator"
                for message in model.inputs[2]
            )
        )


class TestRuntimeObservability(unittest.TestCase):
    class CapturingGraph:
        def __init__(self, error: Exception = None) -> None:
            self.error = error
            self.config = None

        def invoke(self, inputs: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
            self.config = config
            if self.error is not None:
                raise self.error
            return {"messages": [AIMessage(content="answer") ]}

    def _runtime(self) -> MemoryRuntime:
        return MemoryRuntime(checkpointer=MemorySaver(), store=InMemoryStore())

    def test_invoke_config_contains_langsmith_metadata_and_recursion_limit(self) -> None:
        graph = self.CapturingGraph()
        with patch("app.runtime.build_memory_agent_graph", return_value=graph):
            answer = self._runtime().generate_answer_with_memory(
                llm=object(),
                system_prompt="",
                question="question",
                thread_id="thread-observe",
                user_id="user-observe",
            )

        self.assertEqual(answer, "answer")
        self.assertEqual(graph.config["recursion_limit"], GRAPH_RECURSION_LIMIT)
        self.assertEqual(graph.config["recursion_limit"], 10)
        self.assertEqual(graph.config["metadata"]["thread_id"], "thread-observe")
        self.assertEqual(graph.config["metadata"]["entrypoint"], "chat_service.api.chat")
        self.assertIn("api-chat", graph.config["tags"])

    def test_recursion_limit_returns_user_facing_answer(self) -> None:
        graph = self.CapturingGraph(error=GraphRecursionError("limit reached"))
        with patch("app.runtime.build_memory_agent_graph", return_value=graph):
            answer = self._runtime().generate_answer_with_memory(
                llm=object(),
                system_prompt="",
                question="loop forever",
                thread_id="thread-loop",
                user_id="user-loop",
            )

        self.assertEqual(answer, RECURSION_LIMIT_ANSWER)


if __name__ == "__main__":
    unittest.main()