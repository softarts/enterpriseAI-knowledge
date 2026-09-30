"""Long-term memory (V2) verification: store, tool loop, isolation, degradation."""

from __future__ import annotations

import os
import sys
import unittest

_current_dir = os.path.abspath(os.path.dirname(__file__))
_parent_dir = os.path.abspath(os.path.join(_current_dir, ".."))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.long_memory import (
    get_user_memory_namespace,
    retrieve_user_memories,
    save_user_memory,
)
from app.long_memory_prompts import MemoryExtraction
from app.graph import build_memory_agent_graph
from test_helpers import DeterministicMockChatModel, create_test_store


USER_A = "user_A"
USER_B = "user_B"
PYTHON_MEMORY = "用户偏好使用 Python 进行后端开发。"
COFFEE_MEMORY = "用户喜欢手冲咖啡。"


def _config(thread_id: str, user_id: str, top_k: int = 3) -> dict:
    return {"configurable": {"thread_id": thread_id, "user_id": user_id, "top_k": top_k}}


def _tool_calling_model() -> DeterministicMockChatModel:
    def respond(messages):
        last = messages[-1]
        if getattr(last, "type", "") == "tool":
            return f"根据长期记忆回答：{last.content}"
        return "常规回答。"

    return DeterministicMockChatModel(
        response_generator=respond,
        pending_tool_call={
            "name": "search_memory",
            "args": {"query": "用户偏好的编程语言"},
        },
    )


class TestLongTermMemory(unittest.TestCase):
    def test_cross_thread_retrieval_same_user(self) -> None:
        """Memory written under thread t1 is retrievable from thread t2."""
        store = create_test_store()
        self.assertTrue(
            save_user_memory(
                store, USER_A, PYTHON_MEMORY, thread_id="thread_t1", message_id="m1"
            )
        )
        graph = build_memory_agent_graph(
            llm=_tool_calling_model(),
            checkpointer=MemorySaver(),
            store=store,
        )
        result = graph.invoke(
            {"messages": [HumanMessage(content="我适合用什么语言写后端？")]},
            config=_config("thread_t2", USER_A),
        )
        final_answer = result["messages"][-1].content
        self.assertIn("Python", final_answer)

    def test_user_isolation(self) -> None:
        """User B cannot read User A's memories (namespace isolation)."""
        store = create_test_store()
        save_user_memory(store, USER_A, PYTHON_MEMORY, thread_id="thread_t1")

        self.assertEqual(retrieve_user_memories(store, USER_B, "编程语言"), [])
        hits = retrieve_user_memories(store, USER_A, "编程语言")
        self.assertEqual(hits, [PYTHON_MEMORY])

        graph = build_memory_agent_graph(
            llm=_tool_calling_model(),
            checkpointer=MemorySaver(),
            store=store,
        )
        result = graph.invoke(
            {"messages": [HumanMessage(content="我适合用什么语言写后端？")]},
            config=_config("thread_t3", USER_B),
        )
        final_answer = result["messages"][-1].content
        self.assertNotIn("Python", final_answer)
        self.assertIn("没有找到", final_answer)

    def test_semantic_search_hits_relevant_memory(self) -> None:
        """A similar query ranks the semantically related memory first."""
        store = create_test_store()
        save_user_memory(store, USER_A, COFFEE_MEMORY, thread_id="t")
        save_user_memory(store, USER_A, PYTHON_MEMORY, thread_id="t")

        hits = retrieve_user_memories(store, USER_A, "后端编程语言 Python 偏好", top_k=1)
        self.assertEqual(hits, [PYTHON_MEMORY])

    def test_extraction_writes_memory_after_answer(self) -> None:
        """update_memory node stores extracted facts after the final answer."""
        store = create_test_store()
        llm = DeterministicMockChatModel(
            default_response="好的，已记住。",
            structured_result=MemoryExtraction(
                should_store=True, memory="用户是一名后端工程师。"
            ),
        )
        graph = build_memory_agent_graph(
            llm=llm, checkpointer=MemorySaver(), store=store
        )
        result = graph.invoke(
            {"messages": [HumanMessage(content="请记住：我是一名后端工程师。")]},
            config=_config("thread_t4", USER_A),
        )
        self.assertEqual(result["messages"][-1].content, "好的，已记住。")
        namespace = get_user_memory_namespace(USER_A)
        stored = [item.value["content"] for item in store.search(namespace, limit=10)]
        self.assertEqual(stored, ["用户是一名后端工程师。"])

    def test_non_memory_question_not_written(self) -> None:
        """Extraction returning should_store=False leaves the store empty."""
        store = create_test_store()
        llm = DeterministicMockChatModel(
            default_response="12*8 等于 96。",
            structured_result=MemoryExtraction(should_store=False, memory=None),
        )
        graph = build_memory_agent_graph(
            llm=llm, checkpointer=MemorySaver(), store=store
        )
        graph.invoke(
            {"messages": [HumanMessage(content="帮我算一下 12*8 等于多少")]},
            config=_config("thread_t5", USER_A),
        )
        namespace = get_user_memory_namespace(USER_A)
        self.assertEqual(list(store.search(namespace, limit=10)), [])

    def test_store_failure_degrades_gracefully(self) -> None:
        """A failing store does not break the answer path."""

        class FailingSearchStore(InMemoryStore):
            def search(self, *args, **kwargs):
                raise RuntimeError("store unavailable")

        store = FailingSearchStore()
        graph = build_memory_agent_graph(
            llm=_tool_calling_model(),
            checkpointer=MemorySaver(),
            store=store,
        )
        result = graph.invoke(
            {"messages": [HumanMessage(content="我适合用什么语言写后端？")]},
            config=_config("thread_t6", USER_A),
        )
        final_answer = result["messages"][-1].content
        self.assertIn("根据长期记忆回答", final_answer)
        self.assertIn("没有找到", final_answer)

    def test_short_term_history_still_restored_with_store_bound(self) -> None:
        """Checkpointer keeps restoring same-thread history with V2 enabled."""
        def respond(messages):
            full_context = " ".join(
                str(message.content) for message in messages if hasattr(message, "content")
            )
            if "Alice" in full_context and "叫什么名字" in str(messages[-1].content):
                return "你叫 Alice。"
            return "收到。"

        graph = build_memory_agent_graph(
            llm=DeterministicMockChatModel(response_generator=respond),
            checkpointer=MemorySaver(),
            store=create_test_store(),
        )
        config = _config("thread_t7", USER_A)
        graph.invoke({"messages": [HumanMessage(content="我的名字是 Alice。")]}, config=config)
        second = graph.invoke(
            {"messages": [HumanMessage(content="我叫什么名字？")]}, config=config
        )
        self.assertEqual(len(second["messages"]), 4)
        self.assertIn("Alice", second["messages"][-1].content)


if __name__ == "__main__":
    unittest.main()
