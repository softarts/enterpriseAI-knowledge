"""
qa_service.llm_client — LangChain LCEL chain 封装。

使用 langchain-openai 的 ChatOpenAI（OpenAI 兼容接口），
通过环境变量切换 provider（HF Router / LM Studio / 其他）：
    LLM_BASE_URL   e.g. https://router.huggingface.co/v1
    LLM_MODEL      e.g. openai/gpt-oss-120b
    LLM_API_KEY    HF 用 HF_TOKEN 的值；本地模型填任意非空字符串

LCEL chain：ChatPromptTemplate | ChatOpenAI | StrOutputParser
"""

from __future__ import annotations

import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from qa_service import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# system 变量由 pipeline 传入（包含已渲染 context 的 SYSTEM_PROMPT）
# ---------------------------------------------------------------------------

_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "{system_prompt}"),
        ("human", "{question}"),
    ]
)

# ---------------------------------------------------------------------------
# LLM（在首次调用时才真正发出网络请求，模块导入不产生副作用）
# ---------------------------------------------------------------------------


def _build_llm() -> ChatOpenAI:
    """构建 ChatOpenAI 实例，每次调用 generate() 时复用同一实例。"""
    if not config.LLM_BASE_URL:
        raise EnvironmentError(
            "环境变量 LLM_BASE_URL 未设置。"
            "请设置 OpenAI 兼容 endpoint，例如：\n"
            "  export LLM_BASE_URL=https://router.huggingface.co/v1"
        )
    if not config.LLM_MODEL:
        raise EnvironmentError(
            "环境变量 LLM_MODEL 未设置。"
            "请指定模型 id，例如：\n"
            "  export LLM_MODEL=openai/gpt-oss-120b"
        )
    if not config.LLM_API_KEY:
        raise EnvironmentError(
            "环境变量 LLM_API_KEY 未设置。"
            "HF 场景请设置为 HF_TOKEN 的值；本地模型填任意非空字符串。"
        )
    return ChatOpenAI(
        model=config.LLM_MODEL,
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
        temperature=0,
        max_tokens=config.LLM_MAX_TOKENS,
    )


_llm: ChatOpenAI | None = None


def _get_chain():
    """返回（懒加载构建的）LCEL chain。"""
    global _llm
    if _llm is None:
        _llm = _build_llm()
        logger.info(
            "LLM chain initialized: model=%s, base_url=%s, max_tokens=%d",
            config.LLM_MODEL,
            config.LLM_BASE_URL,
            config.LLM_MAX_TOKENS,
        )
    return _PROMPT | _llm | StrOutputParser()


def generate(system_prompt: str, context: str, question: str) -> str:
    """
    组装 prompt 并调用 LLM，返回纯文本答案。

    system_prompt 中包含 {context} 占位符，已在 prompt_builder.SYSTEM_PROMPT
    中定义好；调用方在传入前需先将 context 填入 system_prompt。

    Args:
        system_prompt: 已包含 context 内容的完整 system 指令（由 pipeline 传入）。
        context:       仅用于日志记录（长度信息），不再插入 prompt。
        question:      用户问题原文。

    Returns:
        LLM 返回的答案文本（temperature=0）。
    """
    chain = _get_chain()
    logger.info(
        "Calling LLM: question_len=%d, context_len=%d",
        len(question),
        len(context),
    )
    answer: str = chain.invoke(
        {
            "system_prompt": system_prompt,
            "question": question,
        }
    )
    logger.info("LLM response received: answer_len=%d", len(answer))
    return answer
