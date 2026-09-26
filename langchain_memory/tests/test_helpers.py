"""Test utilities, deterministic mock chat models, and mock embeddings."""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel


class DeterministicMockChatModel(BaseChatModel):
    """
    Mock chat model for deterministic testing of LangGraph workflows.

    - Supports dynamic response generation based on input messages.
    - Implements with_structured_output for memory extraction testing without network.
    - Implements bind_tools/tool_calls for testing the LLM-decides-to-search-memory flow:
      `tool_call_rule(messages)` inspects the conversation so far and, if it
      returns a dict, the mock emits an AIMessage requesting that tool call
      instead of a final answer (once per turn, before any ToolMessage exists).
    """

    response_generator: Optional[Callable[[List[BaseMessage]], str]] = None
    default_response: str = "你好！"
    extraction_rule: Optional[Callable[[str], Any]] = None
    tool_call_rule: Optional[Callable[[List[BaseMessage]], Optional[Dict[str, Any]]]] = None

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.tool_call_rule is not None:
            tool_already_called = any(
                getattr(message, "type", "") == "tool" for message in messages
            )
            if not tool_already_called:
                decision = self.tool_call_rule(messages)
                if decision:
                    ai_message = AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": decision["name"],
                                "args": decision.get("args", {}),
                                "id": "mock_call_1",
                            }
                        ],
                    )
                    return ChatResult(generations=[ChatGeneration(message=ai_message)])

        if self.response_generator:
            text = self.response_generator(messages)
        else:
            text = self.default_response
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    @property
    def _llm_type(self) -> str:
        return "deterministic-mock-chat"

    def bind_tools(self, tools: Any, *, tool_choice: Optional[str] = None, **kwargs: Any) -> "DeterministicMockChatModel":
        # The mock decides tool calls via `tool_call_rule` based on message
        # content, so binding tools is a no-op beyond returning self.
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        rule = self.extraction_rule

        class StructuredOutputRunnable:
            def invoke(self, input_data: Any, config: Optional[Dict[str, Any]] = None) -> Any:
                # Extract text from input messages
                user_text = ""
                if isinstance(input_data, list):
                    for msg in input_data:
                        if hasattr(msg, "content"):
                            user_text += f" {msg.content}"
                elif isinstance(input_data, str):
                    user_text = input_data

                if rule:
                    return rule(user_text)

                # Default fallback heuristic:
                if "安静" in user_text and "餐厅" in user_text:
                    return schema(should_store=True, memory="用户喜欢安静的餐厅。")
                if "日本料理" in user_text:
                    return schema(should_store=True, memory="用户喜欢日本料理。")
                return schema(should_store=False, memory=None)

        return StructuredOutputRunnable()



class KeywordBagEmbeddings(Embeddings):
    """Deterministic embedding generator using keyword presence vectors for semantic test verification."""

    KEYWORDS = [
        "安静",
        "餐厅",
        "日本",
        "料理",
        "工作",
        "晚饭",
        "地方",
        "新加坡",
        "素食",
        "海鲜",
    ]

    def _vectorize(self, text: str) -> List[float]:
        vec = [1.0 if kw in text else 0.0 for kw in self.KEYWORDS]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._vectorize(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._vectorize(text)

