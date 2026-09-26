"""Interactive demonstration entry point for LangGraph Memory MVP V1."""

from __future__ import annotations

import sys
from langchain_core.messages import HumanMessage

from app.graph import build_memory_graph


def _search_memory_results(turn: dict) -> list:
    """Pull out the `search_memory` tool results the agent chose to request."""
    return [
        message.content
        for message in turn.get("messages", [])
        if getattr(message, "type", "") == "tool" and getattr(message, "name", None) == "search_memory"
    ]



def run_demo() -> None:
    print("=" * 60)
    print("LangGraph Memory MVP V1 Demo")
    print("=" * 60)

    graph = build_memory_graph()

    # Demonstration 1: Short-term memory (within the same thread)
    print("\n--- 1. Short-term Memory (Same thread_id) ---")
    config_thread_a = {
        "configurable": {
            "thread_id": "thread_demo_1",
            "user_id": "alice",
        }
    }

    turn1 = graph.invoke(
        {"messages": [HumanMessage(content="你好，我的名字是 Alice。")]},
        config=config_thread_a,
    )
    print(f"Alice (Turn 1): 你好，我的名字是 Alice。")
    print(f"Assistant: {turn1['messages'][-1].content}\n")

    turn2 = graph.invoke(
        {"messages": [HumanMessage(content="我叫什么名字？")]},
        config=config_thread_a,
    )
    print(f"Alice (Turn 2): 我叫什么名字？")
    print(f"Assistant: {turn2['messages'][-1].content}\n")

    # Demonstration 2: Long-term memory (across different threads for same user)
    print("\n--- 2. Long-term Memory (Cross-thread for same user_id) ---")
    turn3 = graph.invoke(
        {"messages": [HumanMessage(content="我特别喜欢安静的日本餐厅。")]},
        config=config_thread_a,
    )
    print(f"Alice (Thread 1): 我特别喜欢安静的日本餐厅。")
    print(f"Assistant: {turn3['messages'][-1].content}\n")

    config_thread_b = {
        "configurable": {
            "thread_id": "thread_demo_2",  # Different thread!
            "user_id": "alice",            # Same user
        }
    }
    turn4 = graph.invoke(
        {"messages": [HumanMessage(content="周末聚餐，你觉得什么样的餐厅适合我？")]},
        config=config_thread_b,
    )
    print(f"Alice (Thread 2): 周末聚餐，你觉得什么样的餐厅适合我？")
    print(f"Assistant: {turn4['messages'][-1].content}")
    print(f"search_memory tool results in Thread 2: {_search_memory_results(turn4)}\n")

    # Demonstration 3: User isolation (different user)
    print("\n--- 3. User Isolation (Different user_id) ---")
    config_bob = {
        "configurable": {
            "thread_id": "thread_bob_1",
            "user_id": "bob",  # Different user!
        }
    }
    turn5 = graph.invoke(
        {"messages": [HumanMessage(content="你觉得什么样的餐厅适合我？")]},
        config=config_bob,
    )
    print(f"Bob: 你觉得什么样的餐厅适合我？")
    print(f"Assistant: {turn5['messages'][-1].content}")
    print(f"search_memory tool results for Bob: {_search_memory_results(turn5)}\n")


if __name__ == "__main__":
    try:
        run_demo()
    except Exception as e:
        print(f"Demo encountered an error (likely due to missing API key): {e}")
        print("Note: To run live with LLM, configure OPENAI_API_KEY / LLM_API_KEY.")
        sys.exit(0)

