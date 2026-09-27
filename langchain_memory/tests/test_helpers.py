"""Deterministic chat model used by LangGraph tests."""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class DeterministicMockChatModel(BaseChatModel):
    """Return deterministic replies based on the messages passed to the model."""

    response_generator: Optional[Callable[[List[BaseMessage]], str]] = None
    default_response: str = "你好！"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = (
            self.response_generator(messages)
            if self.response_generator is not None
            else self.default_response
        )
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    @property
    def _llm_type(self) -> str:
        return "deterministic-mock-chat"
