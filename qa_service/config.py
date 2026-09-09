"""
qa_service 配置。

所有值均可通过环境变量覆盖，无需修改代码。
LLM 相关的三个环境变量（LLM_BASE_URL / LLM_MODEL / LLM_API_KEY）是切换
provider（HF Router → LM Studio → 其他 OpenAI 兼容端点）的唯一入口。

环境变量一览：
    QA_TOP_K                 检索返回的 Top-K 数量（默认 5）
    QA_CONFIDENCE_THRESHOLD  cosine distance 阈值（默认 0.5，见下方注释）
    QA_EMBEDDING_MODEL       embedding 模型名，与 vector_service collection 对应（默认 bge_m3）
    LLM_BASE_URL             OpenAI 兼容端点 base_url（如 https://router.huggingface.co/v1）
    LLM_MODEL                模型 id（如 openai/gpt-oss-120b）
    LLM_API_KEY              API 密钥（HF 用 HF_TOKEN 的值；本地模型填任意字符串）
    LLM_MAX_TOKENS           LLM 最大输出 token 数（默认 1024）
    LLM_ENABLE_THINKING      Qwen3 thinking 模式；默认关闭以保证回答正文有输出
"""

import os

# ---------------------------------------------------------------------------
# 检索配置
# ---------------------------------------------------------------------------

# 每次检索返回的最近邻数量（初始值 5，与 vector_service 默认值一致）
TOP_K: int = int(os.environ.get("QA_TOP_K", "5"))

# 置信度阈值：cosine distance < threshold 才视为"检索到相关内容"并进入生成。
# cosine distance = 1 - cosine similarity，范围 [0, 2]，越小越相似。
# ⚠ 初始值 0.5，未经校准，待有评测数据后调整。
CONFIDENCE_THRESHOLD: float = float(os.environ.get("QA_CONFIDENCE_THRESHOLD", "0.5"))

# embedding 模型名称，必须与写入 ChromaDB 时使用的 collection 对应
EMBEDDING_MODEL: str = os.environ.get("QA_EMBEDDING_MODEL", "bge_m3")

# ---------------------------------------------------------------------------
# LLM 配置（全部从环境变量读取，不硬编码）
# ---------------------------------------------------------------------------

# OpenAI 兼容 base_url；切 LM Studio 只需改此变量，不改代码
LLM_BASE_URL: str = os.environ.get("LLM_BASE_URL", "")

# 模型 id（HF Router 上用 "openai/gpt-oss-120b"）
LLM_MODEL: str = os.environ.get("LLM_MODEL", "")

# API 密钥（HF 场景填 HF_TOKEN 的值；本地模型可填任意非空字符串）
LLM_API_KEY: str = os.environ.get("LLM_API_KEY", "")

# LLM 最大输出 token 数（仅限 completion，不影响 prompt）
LLM_MAX_TOKENS: int = int(os.environ.get("LLM_MAX_TOKENS", "1024"))

# Qwen3 may spend the entire completion budget on reasoning and return an
# empty final content.  None means: use the safe default (disabled) for Qwen
# models, while leaving other OpenAI-compatible models unchanged.
_thinking_env = os.environ.get("LLM_ENABLE_THINKING")
LLM_ENABLE_THINKING: bool | None = (
    None if _thinking_env is None else _thinking_env.strip().lower() in {"1", "true", "yes", "on"}
)
