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
2. 【引用格式优化】请在回答的最后统一列出所有引用来源，使用以下格式：
   **来源：**
   - [文档名称]：chunk_id
   - [文档名称]：chunk_id
   不要在每个句子后面单独标注 [来源: chunk_id]，也不要使用冗长的 chunk ID。
3. 【找不到时明确说】如果 context 中没有足够信息回答问题，直接说"根据现有知识库内容，未能找到与该问题相关的信息。"，不要猜测或补充。
4. 【简洁准确】回答应条理清晰，使用自然流畅的段落而非过度结构化的列表，避免重复 context 原文。
5. 【完整性保证】如果你决定列举多个项目（如场景、步骤、类别等），必须完整覆盖context中提到的所有相关项目，不能中途截断。如果项目较多，建议用概括性段落描述而非逐条列举。

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
