from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List
from unittest.mock import patch

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver

_module_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_tests_dir = os.path.abspath(os.path.dirname(__file__))
if _module_dir not in sys.path:
    sys.path.insert(0, _module_dir)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from app.graph import build_memory_agent_graph
from app.web_search import create_web_search_tool
from test_helpers import DeterministicMockChatModel, create_test_store


class FakeSearchTool:
    def __init__(self, response: Dict[str, Any], error: Exception = None) -> None:
        self.response = response
        self.error = error
        self.call: Dict[str, Any] = {}

    def invoke(self, args: Dict[str, Any]) -> Dict[str, Any]:
        self.call = args
        if self.error:
            raise self.error
        return self.response


class TestWebSearchTool(unittest.TestCase):
    def test_returns_search_snippets_and_source_urls(self) -> None:
        search_tool = FakeSearchTool(
            {
                "results": [
                    {
                        "title": "华为芯片新闻",
                        "url": "https://example.com/news",
                        "content": "一则芯片相关报道。",
                    }
                ]
            }
        )
        search = create_web_search_tool(max_results=3, search_tool=search_tool)

        result = search.invoke({"query": "华为 手机芯片 2026"})

        self.assertIn("华为芯片新闻", result)
        self.assertIn("一则芯片相关报道。", result)
        self.assertIn("https://example.com/news", result)
        self.assertEqual(search_tool.call, {"query": "华为 手机芯片 2026"})

    def test_empty_query_does_not_call_search_tool(self) -> None:
        search_tool = FakeSearchTool({"results": []})
        search = create_web_search_tool(search_tool=search_tool)

        result = search.invoke({"query": "  "})

        self.assertEqual(
            result,
            "Tool failed: query must not be empty. Try a different approach.",
        )
        self.assertEqual(search_tool.call, {})

    def test_missing_api_key_returns_clear_tool_result(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = create_web_search_tool().invoke({"query": "最新手机芯片"})

        self.assertIn("Tool failed: TAVILY_API_KEY is not configured.", result)
        self.assertTrue(result.endswith("Try a different approach."))

    def test_search_failure_returns_clear_tool_result(self) -> None:
        search = create_web_search_tool(
            search_tool=FakeSearchTool({}, error=RuntimeError("upstream unavailable"))
        )

        result = search.invoke({"query": "latest chip"})

        self.assertIn("Tool failed: web search error (RuntimeError).", result)
        self.assertTrue(result.endswith("Try a different approach."))

    def test_default_graph_executes_web_search_then_returns_to_model(self) -> None:
        search_tool = FakeSearchTool(
            {
                "results": [
                    {
                        "title": "芯片发布信息",
                        "content": "华为推出新芯片。",
                        "url": "https://example.com/chip",
                    }
                ]
            }
        )
        web_search = create_web_search_tool(search_tool=search_tool)

        def respond(messages):
            if getattr(messages[-1], "type", "") == "tool":
                return f"依据搜索结果回答：{messages[-1].content}"
            return "常规回答。"

        llm = DeterministicMockChatModel(
            response_generator=respond,
            pending_tool_call={
                "name": "web_search",
                "args": {"query": "华为 手机芯片 2026"},
            },
        )
        with patch("app.graph.app_config.HITL_ENABLED", False), patch(
            "app.graph.create_web_search_tool", return_value=web_search
        ):
            graph = build_memory_agent_graph(
                llm=llm,
                checkpointer=MemorySaver(),
                store=create_test_store(),
            )
            result = graph.invoke(
                {"messages": [HumanMessage(content="华为今年推出了什么最新的手机芯片？")]},
                config={"configurable": {"thread_id": "web-search-test"}},
            )

        self.assertEqual(search_tool.call, {"query": "华为 手机芯片 2026"})
        self.assertIn("https://example.com/chip", result["messages"][-1].content)


class _AlwaysSearchChatModel(DeterministicMockChatModel):
    """Always requests ``web_search`` again, no matter how many results it got.

    Simulates the real bug under test: a model that keeps reformulating the
    query instead of answering. Used only to exercise the hard-stop gate;
    `_generate` (invoked when no tools are bound, i.e. the gate's forced
    finalize call, and by `with_structured_output` for `update_memory`)
    returns a plain text answer instead.
    """

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="已达预算上限，未能确认结果。"))]
        )

    def bind_tools(self, tools: List[Any], **kwargs: Any) -> Any:
        class _BoundModel:
            def invoke(self, messages: List[BaseMessage], config: Any = None, **kw: Any) -> AIMessage:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "web_search",
                            "args": {"query": f"query #{len(messages)}"},
                            "id": f"call_{len(messages)}",
                            "type": "tool_call",
                        }
                    ],
                )

        return _BoundModel()

    @property
    def _llm_type(self) -> str:
        return "always-search-mock"


class TestSearchBudgetGate(unittest.TestCase):
    def test_hard_stops_web_search_after_budget_and_forces_text_answer(self) -> None:
        search_tool = FakeSearchTool(
            {
                "results": [
                    {
                        "title": "无关结果",
                        "content": "未能匹配到有效信息。",
                        "url": "https://example.com/noop",
                    }
                ]
            }
        )
        web_search = create_web_search_tool(search_tool=search_tool)
        llm = _AlwaysSearchChatModel()

        with patch("app.graph.app_config.HITL_ENABLED", False), patch(
            "app.graph.create_web_search_tool", return_value=web_search
        ):
            graph = build_memory_agent_graph(
                llm=llm,
                checkpointer=MemorySaver(),
                store=create_test_store(),
                web_search_max_calls_per_turn=2,
            )
            result = graph.invoke(
                {"messages": [HumanMessage(content="一个搜不到答案的问题")]},
                config={
                    "configurable": {"thread_id": "search-budget-test"},
                    "recursion_limit": 50,
                },
            )

        search_call_count = sum(
            1
            for message in result["messages"]
            if getattr(message, "type", "") == "tool" and message.name == "web_search"
        )
        self.assertEqual(search_call_count, 2, "must stop calling web_search at the budget")

        final_message = result["messages"][-1]
        self.assertEqual(final_message.content, "已达预算上限，未能确认结果。")
        self.assertFalse(getattr(final_message, "tool_calls", None))


if __name__ == "__main__":
    unittest.main()