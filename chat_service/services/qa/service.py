"""Application-facing entry point for Ask/RAG.

The implementation remains in the reusable top-level ``qa_service`` package;
this adapter gives the chat_service a stable service-layer boundary.
"""

from qa_service.pipeline import answer_question

__all__ = ["answer_question"]
