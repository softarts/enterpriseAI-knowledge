"""Structured-output schema and prompt for long-term memory extraction.

Kept separate from app/prompts.py (short-term system prompt) so that
long-term memory prompts never mix with short-term memory code.
"""

from typing import Optional

from pydantic import BaseModel, Field


class MemoryExtraction(BaseModel):
    """Structured decision produced by the memory-extraction LLM call."""

    should_store: bool = Field(
        description=(
            "True only when the user message contains stable preferences, "
            "long-term background, long-term goals, or information the user "
            "explicitly asked to remember."
        )
    )
    memory: Optional[str] = Field(
        default=None,
        description=(
            "A single self-contained sentence describing the fact to store, "
            "written in third person (e.g. '用户偏好使用 Python 进行后端开发'). "
            "Null when should_store is False."
        ),
    )


MEMORY_EXTRACTION_PROMPT = """你是一个长期记忆提取器。请阅读用户消息，判断其中是否包含值得长期保存的用户信息，并以结构化结果返回。

允许保存的内容（should_store=True）：
- 稳定偏好：例如偏好的编程语言、工具、文档语言、回答风格、通知方式。
- 长期背景：例如用户的角色、团队、负责的项目、技术栈、行业领域。
- 长期目标：例如学习计划、季度目标、正在推进的长期事项。
- 用户明确要求记住的信息：例如「请记住 …」「以后都按 … 处理」。

禁止保存的内容（should_store=False）：
- 临时性问题：一次性的事实问答、检索请求、翻译请求。
- 数学计算或一次性任务：例如「帮我算一下 12*8」。
- 一次性闲聊：寒暄、情绪表达、与长期画像无关的随口内容。
- 包含凭证、密码、密钥等敏感信息的内容。

规则：
- memory 字段必须是一句独立、语义完整、可在未来检索时单独理解的陈述句，用第三人称描述用户。
- 不要改写或扩写用户未表达的信息；不确定时返回 should_store=False。
- 当 should_store=False 时，memory 必须为 null。
"""
