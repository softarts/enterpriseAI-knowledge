"""Live diagnostic: how many web_search calls does a real model/Tavily need
to answer "华为推出的 Pura X View 的芯片是什么规格"?

This is **not** part of the normal green suite: it calls the real LLM
endpoint and the real Tavily search API, using credentials read from the
process environment (``source env.sh`` before running — this file never
reads or echoes env.sh itself, only ``os.environ``). It self-skips whenever
those credentials are absent, so ``unittest discover`` stays network-free
everywhere else.

Run it on its own, e.g.:

    source env.sh
    .venv-py314/bin/python -m unittest langchain_agent.tests.test_live_web_search_budget -v

The budget and recursion limit are both overridden generously here so that
whatever the model does is driven purely by its own search strategy, not by
this script's limits — the point is to observe, not to constrain.
"""

from __future__ import annotations

import os
import sys
import unittest

_module_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _module_dir not in sys.path:
    sys.path.insert(0, _module_dir)

from langchain_core.messages import HumanMessage, ToolMessage  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.errors import GraphRecursionError  # noqa: E402

from app.graph import build_memory_agent_graph  # noqa: E402
from app.tool_layer import calculator, create_web_search_tool, get_current_time  # noqa: E402
from app.long_memory import create_search_memory_tool  # noqa: E402

QUESTION = "华为推出的 Pura X View 的芯片是什么规格"

_HAS_LIVE_CREDS = bool(
    os.environ.get("LLM_API_KEY")
    and os.environ.get("LLM_BASE_URL")
    and os.environ.get("TAVILY_API_KEY")
)


def _build_live_llm():
    """Mirror qa_service/llm_client.py's ChatOpenAI construction for the main model."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=os.environ["LLM_MODEL"],
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
        temperature=0,
        max_tokens=int(os.environ.get("LLM_MAX_TOKENS") or 8192),
    )


@unittest.skipUnless(
    _HAS_LIVE_CREDS,
    "live creds not set: source env.sh (needs LLM_API_KEY, LLM_BASE_URL, TAVILY_API_KEY)",
)
class LiveWebSearchBudgetDiagnostic(unittest.TestCase):
    """Drives the real graph once and prints every web_search attempt."""

    def _run_once(self, max_calls_per_turn: int) -> None:
        llm = _build_live_llm()
        graph = build_memory_agent_graph(
            llm=llm,
            checkpointer=MemorySaver(),
            tools=[
                create_search_memory_tool(default_top_k=3),
                create_web_search_tool(),
                calculator,
                get_current_time,
            ],
            web_search_max_calls_per_turn=max_calls_per_turn,
        )
        config = {
            "configurable": {"thread_id": f"live-diag-{max_calls_per_turn}", "user_id": "diag"},
            # Generous: isolate the web_search budget from the global step cap.
            "recursion_limit": 50,
        }

        print(f"\n{'=' * 70}\nweb_search_max_calls_per_turn={max_calls_per_turn}\n{'=' * 70}")
        try:
            result = graph.invoke({"messages": [HumanMessage(content=QUESTION)]}, config=config)
        except GraphRecursionError:
            print("GraphRecursionError: global step cap hit before the model finished.")
            return

        messages = result.get("messages", [])
        search_calls = [
            m for m in messages if isinstance(m, ToolMessage) and m.name == "web_search"
        ]
        print(f"web_search calls made: {len(search_calls)}")
        for i, tm in enumerate(search_calls, start=1):
            content = tm.content if isinstance(tm.content, str) else str(tm.content)
            print(f"\n--- search #{i} (status={tm.status}) ---")
            print(content[:1000])

        final_answer = messages[-1].content if messages else ""
        print(f"\n--- final answer ---\n{final_answer}\n")

    def test_default_budget(self) -> None:
        """Current production default (WEB_SEARCH_MAX_CALLS_PER_TURN=3)."""
        self._run_once(max_calls_per_turn=3)

    def test_higher_budget(self) -> None:
        """More budget: does the question resolve with more search attempts,
        or does Tavily simply have nothing for this product name regardless?
        """
        self._run_once(max_calls_per_turn=6)


if __name__ == "__main__":
    unittest.main()
