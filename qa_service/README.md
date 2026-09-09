# qa_service — 最简版 RAG 问答层

> **阶段**：Phase 2 — 单次检索 + 单次生成（无循环、无多轮）  
> **完成日期**：2026-09-08  
> **状态**：核心流程已跑通；Reflection 为占位实现，下阶段替换

---

## 目录

- [任务背景](#任务背景)
- [模块结构](#模块结构)
- [完整代码流程](#完整代码流程)
- [数据流示例](#数据流示例)
- [LLM 编排细节（LCEL）](#llm-编排细节lcel)
- [Context 与 Prompt 示例](#context-与-prompt-示例)
- [Reflection 接口说明](#reflection-接口说明)
- [环境变量配置](#环境变量配置)
- [API 端点](#api-端点)
- [前端集成](#前端集成)
- [置信度阈值说明](#置信度阈值说明)
- [下一阶段任务](#下一阶段任务)
- [本次未完成事项](#本次未完成事项)
- [依赖关系图](#依赖关系图)

---

## 任务背景

在已完成的以下基础设施之上构建问答层：

| 已完成 | 说明 |
|---|---|
| `embedding_service` (bge-m3) | 文档解析、chunking、向量编码（1024 维，L2 归一化） |
| `vector_service` (ChromaDB) | 向量持久化、Top-K 余弦距离检索 |
| `chat_service` | FastAPI 后端 + React 前端（直连 HF LLM，无 RAG） |

本阶段目标：
- 实现最简 RAG 流程：检索一次 → 生成一次 → 返回答案+引用
- 使用 LangChain LCEL 编排 LLM（不用高层封装如 `RetrievalQA`）
- 预留 Reflection 扩展接口（本次只实现占位，不改动 pipeline 调用方式）
- 新增前端 "Ask" 页面，复用现有 Chat 布局

**核心约束（不因"最简版"而放松）：**
1. LLM 只能基于检索到的 chunk 内容回答，禁止使用模型自身知识补充事实
2. 置信度不够或检索为空，直接返回"未找到相关信息"，不调用 LLM
3. LLM 回答必须标注引用的 chunk_id

---

## 模块结构

```
qa_service/               ← 与 embedding_service/、vector_service/ 同级（项目根）
├── __init__.py           ← 包入口 + 模块说明注释
├── models.py             ← 内部 DTO（RetrievedChunk / ReflectionResult / AnswerResult）
├── config.py             ← 所有配置项，全部支持环境变量覆盖
├── retrieval.py          ← 向量编码 + ChromaDB 检索 + 置信度判断
├── prompt_builder.py     ← context 拼接 + SYSTEM_PROMPT 常量
├── llm_client.py         ← LangChain LCEL chain 封装（ChatOpenAI）
├── reflection.py         ← Reflection 接口 + 占位实现
└── pipeline.py           ← 主入口 answer_question()

chat_service/
├── api/
│   └── routes_ask.py     ← POST /api/ask 端点（新增）
└── main.py               ← 注册 ask_router（已修改）

chat_service/frontend/src/
├── api/
│   └── askApi.js         ← askWithRAG() fetch wrapper（新增）
├── components/
│   ├── AskWindow.jsx     ← Ask 页面主组件，渲染来源 + Reflection badge（新增）
│   └── Sidebar.jsx       ← 新增 "🔍 Ask" 导航项（已修改）
└── App.jsx               ← 新增 ask 视图分支和状态（已修改）
```

---

## 完整代码流程

```
用户问题 (str)
    │
    ▼ pipeline.answer_question()          [pipeline.py L32]
    │
    ├─ Step 1: retrieval.retrieve(question, k=5)   [retrieval.py L45]
    │          │
    │          ├─ _get_embedder().embed_query()    [retrieval.py L64]
    │          │  └─ embedding_service.bge_m3 → query_vector (1024-dim)
    │          │
    │          └─ _get_store().query(query_vector) [retrieval.py L65]
    │             └─ ChromaStore.query() → List[VectorSearchResult]
    │             └─ 转换为 List[RetrievedChunk]  [retrieval.py L68-80]
    │
    ├─ Step 2: retrieval.is_confident(chunks)      [retrieval.py L90]
    │          └─ chunks[0].distance < 0.5?
    │             ├─ No  → 返回 AnswerResult(answer="未找到相关信息")
    │             │         ← 不调用 LLM，直接返回
    │             └─ Yes → 继续
    │
    ├─ Step 3: prompt_builder.build_context(chunks)[prompt_builder.py L37]
    │          └─ 拼接格式：
    │             [来源: doc_id/chunk_id | heading]
    │             chunk 正文
    │             --- (分隔符)
    │
    ├─ Step 4: SYSTEM_PROMPT.format(context=context)[pipeline.py L62]
    │          └─ 将 context 注入 system prompt 的 {context} 占位符
    │
    ├─ Step 5: llm_client.generate(system_prompt, context, question)
    │          │                                  [llm_client.py L87]
    │          └─ LangChain LCEL chain:
    │             ChatPromptTemplate               [llm_client.py L30]
    │             | ChatOpenAI(temperature=0)      [llm_client.py L61]
    │             | StrOutputParser()              [llm_client.py L84]
    │             → draft_answer (str)
    │
    ├─ Step 6: reflection.reflect(draft, context, chunks)
    │          │                                  [reflection.py L26]
    │          └─ 当前：占位实现，直接返回 passed=True
    │             下阶段：逐句比对 chunk 支撑
    │
    └─ 返回 AnswerResult(
           answer=final_answer,
           sources=[chunk_id, ...],
           passed_reflection=True/False/None
       )                                          [pipeline.py L70-74]
```

### 单例加载策略

`retrieval.py` 中 embedder 和 ChromaStore 均为模块级单例（L26-27），仅在首次请求时初始化，后续请求复用：

```python
# retrieval.py L25-42
_embedder = None  # 首次 retrieve() 时加载 bge-m3 模型
_store = None     # 首次 retrieve() 时连接 ChromaDB

def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = get_embedder(config.EMBEDDING_MODEL)
    return _embedder
```

---

## 数据流示例

### 示例 1：正常路径（找到答案）

**问题：** `"SaaS 超过 $250k 需要谁审批？"`

```
Step 1: retrieve()
  → query_vector = bge_m3.embed_query("SaaS 超过 $250k 需要谁审批？")
  → ChromaDB Top-5 结果：
    [rank=1, chunk_id="revrec_001_c3", distance=0.182, doc="Signature Authority..."]
    [rank=2, chunk_id="revrec_001_c7", distance=0.241, doc="CFO approval..."]
    ...

Step 2: is_confident([chunks])
  → chunks[0].distance = 0.182 < 0.5  →  True，继续

Step 3: build_context()
  → "[来源: revrec_001/revrec_001_c3 | Signature Authority]\n..."
    "---"
    "[来源: revrec_001/revrec_001_c7 | CFO Approval]\n..."

Step 4: SYSTEM_PROMPT.format(context=...) → 完整 system 指令

Step 5: LLM 生成
  → "SaaS 合同超过 $250k 时需要 CFO 和 General Counsel 共同审批。
     [来源: revrec_001_c3]"

Step 6: reflect() → passed=True（占位）

返回：
  AnswerResult(
    answer="SaaS 合同超过 $250k 时需要 CFO 和 General Counsel...",
    sources=["revrec_001_c3", "revrec_001_c7", ...],
    passed_reflection=True
  )
```

### 示例 2：阈值拦截（离题问题）

**问题：** `"Python 如何安装 pip？"`

```
Step 1: retrieve()
  → ChromaDB Top-5 结果（均为语料库内容，与 pip 无关）：
    [rank=1, chunk_id="some_chunk", distance=0.73]  ← 距离 > 0.5

Step 2: is_confident()
  → chunks[0].distance = 0.73 >= 0.5  →  False

返回（不调用 LLM）：
  AnswerResult(
    answer="根据现有知识库内容，未能找到与该问题相关的信息。",
    sources=[],
    passed_reflection=None
  )
```

---

## LLM 编排细节（LCEL）

### LCEL Chain 结构

```python
# llm_client.py L30-35, L61-67, L84
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# 1. Prompt 模板：system 已包含完整 context，human 是用户原始问题
_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),   # system_prompt 由 pipeline 传入（含 context）
    ("human", "{question}"),
])

# 2. LLM（懒加载，模块导入时不产生副作用）
_llm = ChatOpenAI(
    model=config.LLM_MODEL,          # 从环境变量读取，不硬编码
    base_url=config.LLM_BASE_URL,    # 从环境变量读取（切 LM Studio 只改此项）
    api_key=config.LLM_API_KEY,      # 从环境变量读取（HF_TOKEN 的值）
    temperature=0,                    # 强制确定性输出
    max_tokens=config.LLM_MAX_TOKENS,
)

# 3. LCEL chain：Runnable 串联，| 是 pipe 运算符
chain = _PROMPT | _llm | StrOutputParser()

# 4. 调用
answer = chain.invoke({
    "system_prompt": "你是...\n<context>\n[来源: ...]...\n</context>",
    "question": "SaaS 超过 $250k 需要谁审批？",
})
# → str 答案
```

### 为什么不用 RetrievalQA / create_retrieval_chain

LangChain 的 `RetrievalQA` 等高层 chain 会内置 retriever 抽象，但本项目的检索已由 `vector_service.ChromaStore` 独立完成，且不需要经过 LangChain 的 Chroma 包装。使用 LCEL 只对 "prompt 组装 → LLM 调用 → 输出解析" 这三步做编排，保持检索层完全独立。

### 切换 LLM Provider

修改三个环境变量，代码一行不改：

| 场景 | LLM_BASE_URL | LLM_MODEL | LLM_API_KEY |
|---|---|---|---|
| HF Router (当前) | `https://router.huggingface.co/v1` | `openai/gpt-oss-120b` | HF_TOKEN 的值 |
| LM Studio (本地) | `http://localhost:1234/v1` | 本地模型名 | 任意非空字符串 |
| OpenAI 官方 | `https://api.openai.com/v1` | `gpt-4o` | OpenAI API Key |

---

## Context 与 Prompt 示例

### build_context() 输出格式

```
# prompt_builder.py L51-56

[来源: procurement_playbook/proc_001_c4 | Approval Requirements]
For SaaS agreements over $250,000, approval is required from the CFO
and General Counsel prior to execution.

---

[来源: procurement_playbook/proc_001_c11 | Multi-Year Commitments]
Multi-year commitments require CFO + General Counsel sign-off regardless
of contract value.

---

[来源: revrec_playbook/rev_001_c2]
Revenue recognition for subscription contracts follows ASC 606...
```

### 完整 SYSTEM_PROMPT 结构

```
# prompt_builder.py L19-35

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
[来源: proc_001/proc_001_c4 | Approval Requirements]
For SaaS agreements over $250,000...

---

[来源: proc_001/proc_001_c11 | Multi-Year Commitments]
Multi-year commitments require CFO...
</context>
```

### 回答格式优化示例

**优化前（过度结构化，引用分散）：**
```
Based on the provided knowledge base, the organization (Redwood Inference) follows ASC 606-aligned principles for revenue recognition and transaction price allocation. The process involves five key steps:

1. Identify the contract: A signed agreement that creates enforceable rights with a customer is required [来源: b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0-chunk-001].
2. Identify performance obligations: These are discrete deliverables such as API access, compute hours, or embeddings delivery [来源: b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0-chunk-001].
3. Determine transaction price: This includes discounts, usage estimates, and variable consideration (subject to constraints) [来源: b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0-chunk-001].
```

**优化后（简洁流畅，引用统一）：**
```
Redwood Inference recognizes customer revenue using ASC 606-aligned principles. It identifies distinct performance obligations, determines the transaction price, allocates it across deliverables based on standalone selling prices or their best estimates, and recognizes revenue when or as each obligation is satisfied.

**来源：**
- [Procurement Contracts and RevRec Playbook]：revrec_001_c1
- [Procurement Contracts and RevRec Playbook]：revrec_001_c2
```

**优化要点：**
1. **避免过度结构化** - 使用自然流畅的段落代替强制编号列表
2. **统一引用位置** - 将所有来源标注移至回答末尾，避免打断阅读流畅性
3. **简化引用格式** - 使用文档名称+简短chunk_id，避免冗长的哈希值
4. **匹配查询复杂度** - 对于中等难度的语义查询，简洁段落比详细分解更合适
5. **完整性保证** - 如果列举多个项目，必须完整覆盖context中的所有相关内容，避免中途截断；项目较多时用概括性段落描述

---

## Reflection 接口说明

### 当前行为（占位实现）

```python
# reflection.py L26-63

def reflect(
    draft_answer: str,
    context: str,
    retrieved_chunks: List[RetrievedChunk],
) -> ReflectionResult:
    # 占位：直接通过，不做任何实际校验
    return ReflectionResult(
        passed=True,
        final_answer=draft_answer,   # == draft_answer，无修改
        notes="占位实现，未做真实校验",
    )
```

### 下阶段替换方式

**只需替换 `reflect()` 函数体，`pipeline.py` 不需要任何改动**：

```python
# pipeline.py L67-68（调用方式，下阶段不变）
reflection_result = reflection.reflect(draft_answer, context, chunks)
# 继续使用 reflection_result.final_answer 和 reflection_result.passed
```

下阶段实现建议方向（见 [下一阶段任务](#下一阶段任务)）。

### ReflectionResult 数据结构

```python
# models.py L28-39

@dataclass
class ReflectionResult:
    passed: bool          # 校验是否通过
    final_answer: str     # 最终答案（通过时 == draft_answer；不通过时为修正后文本）
    notes: str            # 说明信息（调试用，不展示给用户）
```

---

## 环境变量配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_BASE_URL` | `""` (必须设置) | OpenAI 兼容 endpoint |
| `LLM_MODEL` | `""` (必须设置) | 模型 id |
| `LLM_API_KEY` | `""` (必须设置) | API 密钥 |
| `LLM_MAX_TOKENS` | `1024` | LLM 最大输出 token 数 |
| `LLM_ENABLE_THINKING` | Qwen 默认 `false` | Qwen3 是否启用 thinking；启用后可能耗尽输出预算而没有回答正文 |
| `QA_TOP_K` | `5` | 检索 Top-K 数量 |
| `QA_CONFIDENCE_THRESHOLD` | `0.5` | ⚠ cosine distance 阈值，**未经校准** |
| `QA_EMBEDDING_MODEL` | `bge_m3` | embedding 模型名，须与 ChromaDB collection 对应 |

### 启动示例（Windows）

```bat
set LLM_BASE_URL=https://router.huggingface.co/v1
set LLM_MODEL=openai/gpt-oss-120b
set LLM_API_KEY=hf_xxxxxxxxxxxxxxxx

uvicorn chat_service.main:app --reload --port 8100
```

---

## API 端点

### POST `/api/ask`

```http
POST /api/ask
Content-Type: application/json

{
  "question": "multi-year commitments 需要谁审批？"
}
```

**响应（正常路径）：**

```json
{
  "answer": "Multi-year commitments 需要 CFO 和 General Counsel 共同审批。[来源: proc_001_c11]",
  "sources": ["proc_001_c4", "proc_001_c11", "rev_001_c2", "proc_001_c8", "proc_001_c1"],
  "passed_reflection": true,
  "error": null
}
```

**响应（置信度不足）：**

```json
{
  "answer": "根据现有知识库内容，未能找到与该问题相关的信息。",
  "sources": [],
  "passed_reflection": null,
  "error": null
}
```

**响应（LLM 环境变量未配置）：**

```json
{
  "answer": "",
  "sources": [],
  "passed_reflection": null,
  "error": "环境变量 LLM_BASE_URL 未设置。请设置 OpenAI 兼容 endpoint..."
}
```

与 `/api/chat` 的区别：

| | `/api/chat` | `/api/ask` |
|---|---|---|
| 检索 | ❌ 无 | ✅ ChromaDB Top-K |
| LLM 限制 | 无（自由回答） | ✅ 只能基于 context |
| 来源引用 | ❌ | ✅ `sources` 字段 |
| Reflection | ❌ | ✅（当前为占位） |
| trace 字段 | ✅（详细执行步骤） | ❌（未接入 TraceBuilder） |

---

## 前端集成

### 文件改动汇总

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `frontend/src/api/askApi.js` | 新增 | `askWithRAG()` → `POST /api/ask` |
| `frontend/src/components/AskWindow.jsx` | 新增 | 复用 ChatWindow 布局，加来源列表和 Reflection badge |
| `frontend/src/components/Sidebar.jsx` | 修改 L3-6 | MENU 新增 `{ key: "ask", label: "Ask", icon: "🔍" }` |
| `frontend/src/App.jsx` | 修改 | 新增 `askMessages`/`askLoading` 状态 + `handleAskSend` + ask 视图分支 |
| `frontend/src/styles.css` | 修改（末尾追加） | `.ask-message__sources` / `.ask-message__reflection-badge` 样式 |

### AskWindow 独立状态

Ask 视图使用**独立的 `askMessages` / `askLoading` 状态**（`App.jsx` L17-18），切换到 Chat 再切回 Ask，对话历史不丢失：

```jsx
// App.jsx
const [askMessages, setAskMessages] = useState([]);  // Ask 独立消息历史
const [askLoading, setAskLoading]   = useState(false);

// chat 和 ask 各自对应不同的 handler
<ChatWindow messages={messages}    onSend={handleSend}    ... />
<AskWindow  messages={askMessages} onSend={handleAskSend} ... />
```

### 来源引用渲染（AskWindow.jsx）

每条 assistant 消息下方渲染：
- `📎 来源 chunk：` + 每个 chunk_id 以 `<code>` 标签展示
- Reflection badge（绿色 `✓ Reflection` / 红色 `✗ Reflection`）

---

## 置信度阈值说明

```python
# retrieval.py L90-117
# config.py: CONFIDENCE_THRESHOLD = 0.5（环境变量 QA_CONFIDENCE_THRESHOLD）

def is_confident(chunks, threshold=0.5) -> bool:
    if not chunks:
        return False
    return chunks[0].distance < threshold
    # cosine distance = 1 - cosine similarity
    # 范围 [0, 2]，越小越相似
    # 0.5 对应约 cosine similarity = 0.5（中等相似度）
```

> **⚠ 重要**：`0.5` 是初始值，**未经任何校准**。
>
> - 若阈值过低（如 0.3）：很多相关问题会被误判为"找不到"
> - 若阈值过高（如 0.8）：不相关的问题也会进入生成阶段，出现幻觉
>
> 下阶段应基于实际语料的检索评测数据（参考 `embedding_service/evaluation/report/`）来校准。

---

## 下一阶段任务

### P1：Reflection 真实实现（`reflection.py` 函数体替换）

```python
# 当前占位（reflection.py L59-63）
return ReflectionResult(passed=True, final_answer=draft_answer, notes="占位实现")

# 下阶段替换为（pipeline.py 调用方式不变）：
def reflect(draft_answer, context, retrieved_chunks) -> ReflectionResult:
    """
    对 draft_answer 逐句提取断言，检查每句话是否有 retrieved_chunks 支撑。
    实现方案（选其一）：
    
    方案 A：规则方式
      - 提取 draft_answer 中的 [来源: chunk_id] 标注
      - 检查 chunk_id 是否在 retrieved_chunks 列表中
      - 检查引用的 chunk text 是否真的支持该句话
    
    方案 B：独立 LLM 调用（Self-Consistency 校验）
      - 用另一个 LLM 调用，让它判断 draft_answer 的每句话
        是否有 context 支撑，给出 passed/rejected 句子列表
      - 返回修正后的答案（去掉不支持的句子）
    """
```

### P2：Reflection 循环（多轮修正）

若 `reflect()` 返回 `passed=False`，在 `pipeline.py` 中加重试逻辑：

```python
# pipeline.py（下阶段扩展点）
MAX_REFLECTION_ROUNDS = 2
for round in range(MAX_REFLECTION_ROUNDS):
    draft = llm_client.generate(system_prompt, context, question)
    result = reflection.reflect(draft, context, chunks)
    if result.passed:
        break
    # 把 result.notes（修正建议）注入新一轮 prompt
```

### P3：置信度阈值校准

- 基于 `embedding_service/evaluation/evaluation_queries.json`（20 条业务 query）
- 运行不同阈值（0.3 / 0.4 / 0.5 / 0.6）对应的"通过率 vs. 漏检率"
- 在 `embedding_service/evaluation/report/` 下新增阈值校准报告

### P4：ReAct / Plan-and-Execute（未来阶段）

- 当问题需要多步推理时，引入 LangChain Agent / Tool-calling
- `pipeline.py` 的 `answer_question()` 接口签名保持不变

### P5：Trace 接入

- 当前 `/api/ask` 未使用 `chat_service.trace.TraceBuilder`
- 下阶段可在 `routes_ask.py` 中添加 trace，与 `/api/chat` 的 trace 格式对齐
- Ask 页面可复用 `TracePanel.jsx` 展示检索步骤

### P6：端到端评测（测试用例）

本次计划了但暂时未做（见[本次未完成事项](#本次未完成事项)）：

```python
# 计划放在 qa_service/evaluation/test_qa_pipeline.py
# 用例 1：语料库有明确答案 → 验证返回答案 + 非空 sources
# 用例 2：离题问题（如"Python 如何安装 pip"）→ 验证阈值拦截，不调用 LLM
# 用例 3："multi-year commitments 和 SaaS 超过 $250k 分别需要谁审批"
#         → 如实记录检索到的 chunk_id、答案是否覆盖两处信息
```

---

## 本次未完成事项

| 事项 | 原因 | 下阶段计划 |
|---|---|---|
| **端到端测试用例**（3条 pytest） | 用户明确要求"暂时不做测试" | Phase 3（Reflection 实装时一并写） |
| **Reflection 真实校验逻辑** | 按计划本阶段只做接口+占位 | Phase 3，只改 `reflection.py` 函数体 |
| **置信度阈值校准** | 0.5 为初始拍脑袋值，需要评测数据支撑 | Phase 3，配合评测用例一起做 |
| **Ask 页面 Trace 面板** | 当前 Ask 不接入 TraceBuilder，右侧 Trace 面板在 Ask 视图下隐藏 | Phase 3，按需实现 |
| **多轮 Reflection 循环** | 本阶段明确不做 ReAct / 多轮循环 | Phase 4 |
| **ReAct / Plan-and-Execute** | 本阶段明确不做 | 未来阶段 |

---

## 依赖关系图

```
qa_service.pipeline
    ├── qa_service.retrieval
    │       ├── embedding_service.embedder (get_embedder)   ← 不修改
    │       └── vector_service.chroma_store (ChromaStore)   ← 不修改
    ├── qa_service.prompt_builder
    ├── qa_service.llm_client
    │       ├── langchain_openai.ChatOpenAI
    │       └── langchain_core.{prompts, output_parsers}
    ├── qa_service.reflection
    └── qa_service.models

chat_service.api.routes_ask
    └── qa_service.pipeline

chat_service.main
    ├── chat_service.api.routes_chat    ← 不修改（Chat 直连 HF LLM）
    ├── chat_service.api.routes_ask     ← 新增
    └── chat_service.api.routes_import  ← 不修改
```

> **设计原则**：`qa_service` 不依赖 `chat_service` 的任何模块（单向依赖），
> `embedding_service` 和 `vector_service` 的代码一行未改。
