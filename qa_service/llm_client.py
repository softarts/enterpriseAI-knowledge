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
from typing import Any, Dict, Optional

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
    extra_body = None
    is_qwen = "qwen" in config.LLM_MODEL.lower()
    if is_qwen or config.LLM_ENABLE_THINKING is not None:
        enable_thinking = (
            config.LLM_ENABLE_THINKING if config.LLM_ENABLE_THINKING is not None else False
        )
        extra_body = {"chat_template_kwargs": {"enable_thinking": enable_thinking}}
        logger.info("LLM thinking mode: %s", enable_thinking)
    return ChatOpenAI(
        model=config.LLM_MODEL,
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
        temperature=0,
        max_tokens=config.LLM_MAX_TOKENS,
        extra_body=extra_body,
    )


_llm: Optional[ChatOpenAI] = None
_reflection_llm: Optional[ChatOpenAI] = None


def get_llm() -> ChatOpenAI:
    """获取或初始化复用的主 ChatOpenAI 实例。"""
    global _llm
    if _llm is None:
        _llm = _build_llm()
        logger.info(
            "LLM instance initialized: model=%s, base_url=%s, max_tokens=%d",
            config.LLM_MODEL,
            config.LLM_BASE_URL,
            config.LLM_MAX_TOKENS,
        )
    return _llm


def _build_reflection_llm() -> ChatOpenAI:
    """构建 Reflection 专用 ChatOpenAI 实例（支持独立模型或主模型回退）。"""
    base_url = config.get_reflection_base_url()
    model = config.get_reflection_model()
    api_key = config.get_reflection_api_key()

    if not base_url or not model or not api_key:
        raise EnvironmentError(
            f"Reflection endpoint 未完整配置 (base_url={base_url}, model={model})"
        )

    extra_body = None
    is_qwen = "qwen" in model.lower()
    if is_qwen or config.LLM_ENABLE_THINKING is not None:
        enable_thinking = (
            config.LLM_ENABLE_THINKING if config.LLM_ENABLE_THINKING is not None else False
        )
        extra_body = {"chat_template_kwargs": {"enable_thinking": enable_thinking}}
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=0,
        max_tokens=config.LLM_MAX_TOKENS,
        extra_body=extra_body,
    )


def get_reflection_llm() -> ChatOpenAI:
    """获取或初始化 Reflection 专用 ChatOpenAI 实例。"""
    global _reflection_llm
    # 如果独立配置与主模型完全一致，可直接复用主实例
    if (
        config.get_reflection_model() == config.LLM_MODEL
        and config.get_reflection_base_url() == config.LLM_BASE_URL
        and config.get_reflection_api_key() == config.LLM_API_KEY
    ):
        return get_llm()

    if _reflection_llm is None:
        _reflection_llm = _build_reflection_llm()
        logger.info(
            "Reflection LLM instance initialized: model=%s, base_url=%s, max_tokens=%d",
            config.get_reflection_model(),
            config.get_reflection_base_url(),
            config.LLM_MAX_TOKENS,
        )
    return _reflection_llm


def get_model_config() -> Dict[str, Any]:
    """返回当前主 LLM 配置字典（供 trace 记录）。"""
    return {
        "model": config.LLM_MODEL,
        "base_url": config.LLM_BASE_URL,
        "max_tokens": config.LLM_MAX_TOKENS,
        "temperature": 0,
        "thinking_enabled": config.LLM_ENABLE_THINKING,
    }


def get_reflection_model_config() -> Dict[str, Any]:
    """返回当前 Reflection LLM 配置字典（不包含密钥，供 trace 记录）。"""
    return {
        "model": config.get_reflection_model(),
        "base_url": config.get_reflection_base_url(),
        "max_tokens": config.LLM_MAX_TOKENS,
        "temperature": 0,
        "thinking_enabled": config.LLM_ENABLE_THINKING,
    }


def _get_chain():
    """返回（懒加载构建的）LCEL chain。"""
    return _PROMPT | get_llm() | StrOutputParser()


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
        "Calling LLM: question_len=%d, context_len=%d, max_tokens=%d",
        len(question),
        len(context),
        config.LLM_MAX_TOKENS,
    )
    answer: str = chain.invoke(
        {
            "system_prompt": system_prompt,
            "question": question,
        }
    )
    logger.info("LLM response received: answer_len=%d, answer_preview=%s", len(answer), answer[:200] if answer else "empty")
    return answer


def generate_reflection(prompt: str) -> str:
    """
    调用 LLM 执行 Reflection 评审。

    Args:
        prompt: 组装好的完整 Reflection prompt。

    Returns:
        LLM 返回的 Reflection 文本。
    """
    llm = get_reflection_llm()
    model_name = config.get_reflection_model()
    logger.info(
        "Calling Reflection LLM: prompt_len=%d, model=%s, max_tokens=%d",
        len(prompt),
        model_name,
        config.LLM_MAX_TOKENS,
    )
    chain = llm | StrOutputParser()
    result: str = chain.invoke(prompt)
    logger.info(
        "Reflection LLM response received: len=%d, preview=%s",
        len(result),
        result[:200] if result else "empty",
    )
    return result


def generate_revision(prompt: str) -> str:
    """
    调用 LLM 执行 Revision 答案修订。

    Args:
        prompt: 组装好的完整 Revision prompt。

    Returns:
        LLM 返回的修订后答案文本。
    """
    llm = get_llm()
    logger.info(
        "Calling Revision LLM: prompt_len=%d, model=%s, max_tokens=%d",
        len(prompt),
        config.LLM_MODEL,
        config.LLM_MAX_TOKENS,
    )
    chain = llm | StrOutputParser()
    result: str = chain.invoke(prompt)
    logger.info(
        "Revision LLM response received: len=%d, preview=%s",
        len(result),
        result[:200] if result else "empty",
    )
    return result
