"""Deterministic chat model and fakes used by LangGraph tests."""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

import os
import sys

_current_dir = os.path.abspath(os.path.dirname(__file__))
_parent_dir = os.path.abspath(os.path.join(_current_dir, ".."))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from app.long_memory import create_memory_store  # noqa: E402


class DeterministicMockChatModel(BaseChatModel):
    """Return deterministic replies based on the messages passed to the model."""

    response_generator: Optional[Callable[[List[BaseMessage]], str]] = None
    default_response: str = "你好！"
    # When set, the first model call (before any ToolMessage exists) returns an
    # AIMessage carrying this tool call instead of text.
    pending_tool_call: Optional[Dict[str, Any]] = None
    # Returned by with_structured_output(); may be a value or a callable.
    structured_result: Any = None

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.pending_tool_call is not None:
            # Emit the scripted tool call only on the round that has not seen a
            # tool result yet, so the agent loop terminates like the real model.
            has_tool_result = any(
                getattr(message, "type", "") == "tool" for message in messages
            )
            if not has_tool_result:
                call = dict(self.pending_tool_call)
                return ChatResult(
                    generations=[
                        ChatGeneration(
                            message=AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "name": call["name"],
                                        "args": call.get("args", {}),
                                        "id": call.get("id", "call_1"),
                                        "type": "tool_call",
                                    }
                                ],
                            )
                        )
                    ]
                )
        text = (
            self.response_generator(messages)
            if self.response_generator is not None
            else self.default_response
        )
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def bind_tools(self, tools: List[Any], **kwargs: Any) -> Any:
        # Return a *real* RunnableBinding rather than a hand-rolled wrapper:
        # the trace handler reads the per-LLM-call payload from LangChain's own
        # on_chat_model_start / on_llm_end callbacks, which only fire for calls
        # that go through the Runnable machinery. A plain object with an
        # `invoke` method (as this mock used to return) bypasses them entirely.
        return self.bind(
            tools=[convert_to_openai_tool(tool) for tool in tools],
            **kwargs,
        )

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        parent = self

        class _StructuredRunnable:
            def _build_default(self, messages: List[BaseMessage]) -> Any:
                # Schema-agnostic default: reuse whatever _generate() would
                # have answered in plain text and adapt it to the requested
                # schema. Tries an `answer`-shaped schema first (e.g.
                # graph.py's `_FinalAnswer`, used by force_finalize) before
                # falling back to the long-term-memory extraction shape
                # (`MemoryExtraction`, used by update_memory) that this mock
                # originally only supported.
                text = parent._generate(messages).generations[0].message.content
                try:
                    return schema(answer=text)
                except Exception:
                    return schema(should_store=False, memory=None)

            def invoke(self, messages: List[BaseMessage], config: Any = None, **kw: Any) -> Any:
                if callable(parent.structured_result):
                    return parent.structured_result(messages)
                if parent.structured_result is not None:
                    return parent.structured_result
                return self._build_default(messages)

            async def ainvoke(
                self, messages: List[BaseMessage], config: Any = None, **kw: Any
            ) -> Any:
                return self.invoke(messages, config=config, **kw)

        return _StructuredRunnable()

    @property
    def _llm_type(self) -> str:
        return "deterministic-mock-chat"


class HashingEmbeddings(Embeddings):
    """Deterministic local embeddings: hashed word/char-bigram count vectors.

    Texts sharing words or character bigrams get high cosine similarity, so
    semantic-search behaviour can be tested without loading a real model.
    """

    def __init__(self, dims: int = 128) -> None:
        self.dims = dims

    def _vector(self, text: str) -> List[float]:
        vec = [0.0] * self.dims
        lowered = text.lower()
        tokens = lowered.split()
        tokens.extend(lowered[i : i + 2] for i in range(len(lowered) - 1))
        for token in tokens:
            vec[hash(token) % self.dims] += 1.0
        norm = math.sqrt(sum(value * value for value in vec)) or 1.0
        return [value / norm for value in vec]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._vector(text)


def create_test_store(dims: int = 128):
    """InMemoryStore with semantic indexing backed by HashingEmbeddings."""
    return create_memory_store(embeddings=HashingEmbeddings(dims=dims), dims=dims)
