from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict
from unittest.mock import patch

from langchain_core.messages import HumanMessage
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

        self.assertIn("查询内容为空", result)
        self.assertEqual(search_tool.call, {})

    def test_missing_api_key_returns_clear_tool_result(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = create_web_search_tool().invoke({"query": "最新手机芯片"})

        self.assertIn("TAVILY_API_KEY", result)

    def test_search_failure_returns_clear_tool_result(self) -> None:
        search = create_web_search_tool(
            search_tool=FakeSearchTool({}, error=RuntimeError("upstream unavailable"))
        )

        result = search.invoke({"query": "latest chip"})

        self.assertIn("网页搜索暂时失败", result)

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
        with patch("app.graph.create_web_search_tool", return_value=web_search):
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


if __name__ == "__main__":
    unittest.main()