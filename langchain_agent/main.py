"""Interactive demonstration of Checkpointer-backed short-term memory."""

from __future__ import annotations

import sys

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.graph import build_memory_agent_graph


def run_demo() -> None:
    graph = build_memory_agent_graph(checkpointer=MemorySaver())
    thread_config = {"configurable": {"thread_id": "thread_demo_1"}}

    first_turn = graph.invoke(
        {"messages": [HumanMessage(content="你好，我的名字是 Alice。") ]},
        config=thread_config,
    )
    print(f"Alice: 你好，我的名字是 Alice。\nAssistant: {first_turn['messages'][-1].content}\n")

    second_turn = graph.invoke(
        {"messages": [HumanMessage(content="我叫什么名字？")]},
        config=thread_config,
    )
    print(f"Alice: 我叫什么名字？\nAssistant: {second_turn['messages'][-1].content}")


if __name__ == "__main__":
    try:
        run_demo()
    except Exception as exc:
        print(f"Demo encountered an error (likely due to missing API key): {exc}")
        print("Configure OPENAI_API_KEY / LLM_API_KEY to run with a live LLM.")
        sys.exit(0)
