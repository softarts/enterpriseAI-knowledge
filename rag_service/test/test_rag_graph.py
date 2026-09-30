"""rag_service 图编排测试。

覆盖：
    1. 检索置信度不足 → 直接返回"未找到"，不调用 LLM
    2. critic PASS → 保留草稿，revision 步骤 skipped
    3. critic REVISE → revise 成功 → critic 复审 PASS（多轮循环）
    4. revise 失败 → 回退到 draft，路由 finalize
    5. 持续 REVISE → MAX_REVISION 上限终止循环
    6. REFLECTION_ENABLED=false → critic skipped
    7. generate↔tools 死循环 → recursion_limit 安全停止
    8. 同一 thread_id 第二轮由 Checkpointer 自动恢复历史
"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional
from unittest import mock

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import Field

from rag_service import config
from rag_service.models import RetrievedChunk
from rag_service.runtime import RagRuntime


class FakeChatModel(BaseChatModel):
    """脚本化聊天模型：responder 根据传入 messages 生成 AIMessage。"""

    responder: Optional[Callable[[List[BaseMessage]], AIMessage]] = None
    captured: List[List[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = (
            self.responder(messages)
            if self.responder is not None
            else AIMessage(content="草稿答案")
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools: List[Any], **kwargs: Any) -> Any:
        parent = self

        class _BoundModel:
            def invoke(
                self, messages: List[BaseMessage], config: Any = None, **kw: Any
            ) -> AIMessage:
                parent.captured.append(list(messages))
                return parent._generate(messages).generations[0].message

        return _BoundModel()

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        class _StructuredRunnable:
            def invoke(self, messages: List[BaseMessage], config: Any = None, **kw: Any) -> Any:
                return SimpleNamespace(should_store=False, memory="")

        return _StructuredRunnable()


def _tool_calling_responder(messages: List[BaseMessage]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_memory",
                "args": {"query": "用户偏好"},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )


def _make_chunks() -> List[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id="c1",
            document_id="doc1",
            title="Doc 1",
            heading=None,
            source_path="doc1.md",
            text="企业知识内容。",
            distance=0.1,
            rank=1,
        )
    ]


def _reflection_text(decision: str) -> str:
    return (
        f"Decision: {decision}\n\n"
        "Reasons:\n- None\n\n"
        "Unnecessary or out-of-scope content:\n- None\n\n"
        "Missing important information:\n- None\n\n"
        "Unsupported claims:\n- None\n"
    )


def _make_runtime(llm: BaseChatModel) -> RagRuntime:
    return RagRuntime(checkpointer=MemorySaver(), store=InMemoryStore())


def _patch_retrieval(confident: bool):
    return (
        mock.patch("rag_service.retrieval.retrieve", return_value=_make_chunks()),
        mock.patch("rag_service.retrieval.is_confident", return_value=confident),
    )


class RagGraphTest(unittest.TestCase):
    def test_not_confident_returns_not_found_without_llm(self) -> None:
        llm = FakeChatModel()
        runtime = _make_runtime(llm)
        p_retrieve, p_confident = _patch_retrieval(confident=False)
        with p_retrieve, p_confident, mock.patch(
            "rag_service.llm_client.generate_reflection"
        ) as m_reflect:
            result = runtime.answer_question("问题", thread_id="t1", llm=llm)

        self.assertEqual(result.answer, config.NOT_FOUND_ANSWER)
        self.assertEqual(result.sources, [])
        self.assertIsNone(result.passed_reflection)
        self.assertEqual(llm.captured, [])
        m_reflect.assert_not_called()
        step_names = [s["name"] for s in result.trace["steps"]]
        self.assertIn("retrieval", step_names)
        self.assertIn("confidence", step_names)
        self.assertNotIn("llm", step_names)
        self.assertNotIn("reflection", step_names)

    def test_critic_pass_keeps_draft_and_skips_revision(self) -> None:
        llm = FakeChatModel()
        runtime = _make_runtime(llm)
        p_retrieve, p_confident = _patch_retrieval(confident=True)
        with p_retrieve, p_confident, mock.patch(
            "rag_service.llm_client.generate_reflection",
            return_value=_reflection_text("PASS"),
        ) as m_reflect, mock.patch(
            "rag_service.llm_client.generate_revision"
        ) as m_revise:
            result = runtime.answer_question("问题", thread_id="t2", llm=llm)

        self.assertEqual(result.answer, "草稿答案")
        self.assertEqual(result.sources, ["c1"])
        self.assertTrue(result.passed_reflection)
        m_reflect.assert_called_once()
        m_revise.assert_not_called()
        revision_steps = [
            s for s in result.trace["steps"] if s["name"] == "revision"
        ]
        self.assertEqual(len(revision_steps), 1)
        self.assertEqual(revision_steps[0]["status"], "skipped")

    def test_revise_then_pass_loops_back_to_critic(self) -> None:
        llm = FakeChatModel()
        runtime = _make_runtime(llm)
        p_retrieve, p_confident = _patch_retrieval(confident=True)
        with p_retrieve, p_confident, mock.patch(
            "rag_service.llm_client.generate_reflection",
            side_effect=[_reflection_text("REVISE"), _reflection_text("PASS")],
        ) as m_reflect, mock.patch(
            "rag_service.llm_client.generate_revision",
            return_value="修订后答案",
        ) as m_revise:
            result = runtime.answer_question("问题", thread_id="t3", llm=llm)

        self.assertEqual(result.answer, "修订后答案")
        self.assertEqual(m_reflect.call_count, 2)
        m_revise.assert_called_once()
        # checkpoint 中的最终 AI 消息应为修订稿
        checkpoint = runtime.checkpointer.get_tuple(
            {"configurable": {"thread_id": "t3"}}
        )
        messages = checkpoint.checkpoint["channel_values"]["messages"]
        self.assertEqual(messages[-1].content, "修订后答案")

    def test_revision_failure_falls_back_to_draft(self) -> None:
        llm = FakeChatModel()
        runtime = _make_runtime(llm)
        p_retrieve, p_confident = _patch_retrieval(confident=True)
        with p_retrieve, p_confident, mock.patch(
            "rag_service.llm_client.generate_reflection",
            side_effect=[_reflection_text("REVISE")],
        ) as m_reflect, mock.patch(
            "rag_service.llm_client.generate_revision",
            side_effect=RuntimeError("llm down"),
        ):
            result = runtime.answer_question("问题", thread_id="t4", llm=llm)

        self.assertEqual(result.answer, "草稿答案")
        # 修订失败后直接 finalize，critic 只执行一次
        m_reflect.assert_called_once()
        revision_steps = [
            s for s in result.trace["steps"] if s["name"] == "revision"
        ]
        self.assertEqual(len(revision_steps), 1)
        self.assertEqual(revision_steps[0]["status"], "error")

    def test_max_revision_caps_loop(self) -> None:
        llm = FakeChatModel()
        runtime = _make_runtime(llm)
        p_retrieve, p_confident = _patch_retrieval(confident=True)
        with p_retrieve, p_confident, mock.patch.object(
            config, "MAX_REVISION", 2
        ), mock.patch(
            "rag_service.llm_client.generate_reflection",
            side_effect=[_reflection_text("REVISE")] * 10,
        ) as m_reflect, mock.patch(
            "rag_service.llm_client.generate_revision",
            side_effect=["修订稿1", "修订稿2", "修订稿3"],
        ) as m_revise:
            result = runtime.answer_question("问题", thread_id="t5", llm=llm)

        # critic 执行 MAX_REVISION + 1 次，revise 执行 MAX_REVISION 次
        self.assertEqual(m_reflect.call_count, 3)
        self.assertEqual(m_revise.call_count, 2)
        self.assertEqual(result.answer, "修订稿2")
        self.assertFalse(result.passed_reflection)

    def test_reflection_disabled_skips_critic(self) -> None:
        llm = FakeChatModel()
        runtime = _make_runtime(llm)
        p_retrieve, p_confident = _patch_retrieval(confident=True)
        with p_retrieve, p_confident, mock.patch.dict(
            os.environ, {"REFLECTION_ENABLED": "false"}
        ), mock.patch(
            "rag_service.llm_client.generate_reflection"
        ) as m_reflect:
            result = runtime.answer_question("问题", thread_id="t6", llm=llm)

        self.assertEqual(result.answer, "草稿答案")
        self.assertIsNone(result.passed_reflection)
        m_reflect.assert_not_called()
        reflection_steps = [
            s for s in result.trace["steps"] if s["name"] == "reflection"
        ]
        self.assertEqual(len(reflection_steps), 1)
        self.assertEqual(reflection_steps[0]["status"], "skipped")

    def test_recursion_limit_stops_tool_loop(self) -> None:
        llm = FakeChatModel(responder=_tool_calling_responder)
        runtime = _make_runtime(llm)
        p_retrieve, p_confident = _patch_retrieval(confident=True)
        with p_retrieve, p_confident:
            result = runtime.answer_question("问题", thread_id="t7", llm=llm)

        self.assertEqual(result.answer, config.RECURSION_LIMIT_ANSWER)
        self.assertEqual(result.sources, [])

    def test_second_turn_restores_history_via_checkpointer(self) -> None:
        llm = FakeChatModel()
        runtime = _make_runtime(llm)
        p_retrieve, p_confident = _patch_retrieval(confident=True)
        with p_retrieve, p_confident, mock.patch(
            "rag_service.llm_client.generate_reflection",
            return_value=_reflection_text("PASS"),
        ):
            runtime.answer_question("第一轮问题", thread_id="t8", llm=llm)
            result = runtime.answer_question("第二轮问题", thread_id="t8", llm=llm)

        self.assertEqual(result.answer, "草稿答案")
        # 第二轮 generate 收到的 messages 应包含第一轮的 Q&A（SystemMessage 除外）
        second_turn_messages = [
            m for m in llm.captured[-1] if getattr(m, "type", "") != "system"
        ]
        types = [m.type for m in second_turn_messages]
        self.assertEqual(types, ["human", "ai", "human"])
        self.assertEqual(second_turn_messages[0].content, "第一轮问题")
        self.assertEqual(second_turn_messages[-1].content, "第二轮问题")


if __name__ == "__main__":
    unittest.main()
