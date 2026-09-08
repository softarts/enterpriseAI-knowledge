"""
qa_service.prompt_builder — context 组装与 system prompt。

职责：
    build_context()   把 RetrievedChunk 列表拼成可插入 prompt 的纯文本 context
    SYSTEM_PROMPT     送给 LLM 的系统指令常量
"""

from __future__ import annotations

from typing import List

from qa_service.models import RetrievedChunk

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
你是一个企业知识库问答助手。请严格遵守以下规则：

1. 【唯一信息来源】只能依据下方 <context> 标签内提供的内容回答问题，禁止使用你自身的知识补充任何事实。
2. 【必须标注来源】回答中引用了某段内容时，必须在该句末尾以 [来源: chunk_id] 的格式标注对应的 chunk_id。
3. 【找不到时明确说】如果 context 中没有足够信息回答问题，直接说"根据现有知识库内容，未能找到与该问题相关的信息。"，不要猜测或补充。
4. 【简洁准确】回答应条理清晰，避免重复 context 原文，用自然语言总结关键信息。

<context>
{context}
</context>\
"""

# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def build_context(chunks: List[RetrievedChunk]) -> str:
    """
    把检索到的 chunk 列表拼成 context 字符串，插入 system prompt 的 {context} 占位符。

    每个 chunk 的格式：
        [来源: document_id/chunk_id | heading（若有）]
        chunk 正文

    Args:
        chunks: retrieve() 返回的 RetrievedChunk 列表。

    Returns:
        可直接插入 prompt 的纯文本字符串。
    """
    parts: List[str] = []
    for chunk in chunks:
        heading_part = f" | {chunk.heading}" if chunk.heading else ""
        header = f"[来源: {chunk.document_id}/{chunk.chunk_id}{heading_part}]"
        parts.append(f"{header}\n{chunk.text.strip()}")
    return "\n\n---\n\n".join(parts)
