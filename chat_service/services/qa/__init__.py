"""Ask/RAG service entry points used by the HTTP API."""

from chat_service.services.qa.service import answer_question

__all__ = ["answer_question"]
