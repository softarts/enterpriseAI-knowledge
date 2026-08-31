# 企业知识库 POC 系统架构设计

## 1. 项目概述

本项目旨在构建一个企业知识库原型系统（POC），第一阶段以本地运行方式打通：

原始企业文档 → OKF 标准化 → 向量化 → 检索 → RAG 问答 → FastAPI → MCP → Kiro Agent

系统设计遵循“先本地跑通最小闭环，再逐步服务化”的原则。

第一阶段不追求复杂的企业级基础设施，而是重点验证知识标准化、检索质量、RAG 效果以及 Agent 接入方式。

---

## 2. 总体目标

### 2.1 功能目标

系统需要支持：

1. 导入企业内部 PDF、Word、Confluence HTML、TXT 文档。
2. 将原始文档转换为统一的 OKF 格式。
3. 保留原始文档的目录层次、标题、正文及基础 Metadata。
4. 将 OKF 文档进行 Chunking。
5. 使用 Embedding 模型生成向量。
6. 将向量存入 FAISS，完成语义检索。
7. 基于检索结果构建 RAG Context。
8. 调用 LLM 生成企业知识库问答。
9. 使用 FastAPI 提供文档检索和获取接口。
10. 通过 MCP 将知识库能力暴露给 Kiro Agent。
11. 实现 Kiro CLI → MCP → Knowledge Base → Agent Answer 的最小闭环。

### 2.2 第一阶段目标

第一阶段重点是验证以下完整链路是否可行：

```text
10–20 篇企业文档
        ↓
文档导入
        ↓
OKF 标准化
        ↓
Chunking
        ↓
Embedding
        ↓
FAISS
        ↓
Search
        ↓
RAG
        ↓
FastAPI
        ↓
MCP
        ↓
Kiro Agent
        ↓
最终答案
```

第一阶段的核心验收标准不是组件数量，而是：

- 文档能够稳定转换。
- 知识结构能够保留。
- 检索能够召回正确内容。
- LLM 能够基于检索内容回答问题。
- 找不到知识时能够拒绝编造。
- Agent 能够通过 MCP 使用知识库。

---

# 3. 总体架构

## 3.1 分层架构

系统划分为以下七层：

| Layer | 层次 | 主要职责 | 第一阶段实现 |
|---|---|---|---|
| Layer 1 | 输入层 | 接收企业原始文档 | 本地文件 |
| Layer 2 | 标准化与存储层 | 原始文档 → OKF | Python + Markdown + YAML |
| Layer 3 | 向量化层 | Chunking + Embedding + Index | sentence-transformers + FAISS |
| Layer 4 | 检索与生成层 | Retrieval + RAG + LLM | LangChain / LlamaIndex |
| Layer 5 | API 服务层 | 提供 HTTP API | FastAPI |
| Layer 6 | MCP 接口层 | 提供 Agent Tool | MCP Server |
| Layer 7 | Agent 集成层 | Agent 调用知识库并回答 | Kiro Agent |

---

## 3.2 系统逻辑架构

```text
┌─────────────────────────────────────────────────────────────┐
│                    Enterprise Documents                    │
│                                                             │
│        PDF / Word / Confluence HTML / TXT                  │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Layer 1: Document Ingestion                   │
│                                                             │
│ import_raw_doc_to_okf.py                                    │
│ doc_to_okf_config.yaml                                      │
│                                                             │
│ Parser → Cleaner → Structure Detection → Metadata          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│             Layer 2: OKF Standardization / Store           │
│                                                             │
│ YAML Frontmatter + Markdown                                 │
│                                                             │
│ ./generated/documents/                                      │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  Layer 3: Vectorization                    │
│                                                             │
│ Heading-aware Chunking                                      │
│            ↓                                                │
│ Embedding Provider                                          │
│            ↓                                                │
│ FAISS Vector Store                                          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│               Layer 4: Retrieval / RAG                     │
│                                                             │
│ User Query → Query Embedding → Vector Search → Top-K       │
│                                             ↓               │
│                                       Context Builder       │
│                                             ↓               │
│                                            LLM              │
│                                             ↓               │
│                                      Answer + Sources       │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Layer 5: FastAPI                         │
│                                                             │
│ /health                                                     │
│ /documents                                                  │
│ /documents/{document_id}                                    │
│ /search                                                     │
│ /query                                                      │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Layer 6: MCP                            │
│                                                             │
│ list_documents                                              │
│ query_documents                                             │
│ get_document                                                │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  Layer 7: Kiro Agent                       │
│                                                             │
│ User Question → MCP Tool Call → Knowledge Context → LLM   │
│                                      ↓                      │
│                              Final Answer + Sources         │
└─────────────────────────────────────────────────────────────┘
```

---

# 4. Layer 1 - 输入层

## 4.1 数据来源

第一阶段支持以下企业内部文档：

- PDF
- Word / DOCX
- Confluence HTML
- TXT

第一阶段主要通过本地目录导入，不要求直接实现企业系统 Connector。

后续可以扩展：

- Confluence API
- SharePoint
- Google Drive
- 企业网盘
- Git Repository
- 数据库
- 内部 Wiki

---

## 4.2 输入目录

推荐：

```text
input/
├── pdf/
├── word/
├── confluence/
└── txt/
```

也可以按照业务域组织：

```text
input/
├── hr/
│   ├── employee_handbook.pdf
│   └── leave_policy.docx
├── security/
│   ├── security_policy.pdf
│   └── account_policy.docx
└── engineering/
    ├── api_guideline.pdf
    └── development_standard.docx
```

---

# 5. Layer 2 - 文档标准化与 OKF 存储层

## 5.1 核心职责

这一层负责将异构企业文档转换为统一的 OKF 格式。

核心原则：

> 原始文档负责输入，OKF 负责统一知识表达。

后续 RAG、Search、API 和 MCP 不应该直接依赖 PDF、Word 或 Confluence 原始格式，而应该依赖标准化后的 OKF。

---

## 5.2 核心工具

```text
scripts/import_raw_doc_to_okf.py
config/doc_to_okf_config.yaml
```

---

## 5.3 转换流程

```text
Raw Document
    ↓
Parser
    ↓
Content Cleaning
    ↓
Structure Detection
    ↓
Metadata Extraction
    ↓
OKF Writer
    ↓
Markdown + YAML Frontmatter
```

不同格式使用不同 Parser：

| 文档类型 | 推荐工具 |
|---|---|
| PDF | PyMuPDF |
| DOCX | python-docx |
| HTML | BeautifulSoup |
| TXT | Python 原生文件处理 |

---

## 5.4 结构保留

转换时需要尽可能保留原始目录层次。

例如原始文档：

```text
Chapter 1
  1.1 Introduction
  1.2 Scope

Chapter 2
  2.1 Policy
  2.2 Exception
```

OKF：

```markdown
# Chapter 1

## 1.1 Introduction

## 1.2 Scope

# Chapter 2

## 2.1 Policy

## 2.2 Exception
```

这样后续 Chunking 可以基于 Heading 进行语义切分。

---

# 6. OKF 文档格式

推荐每个 OKF 文档包含：

```markdown
---
document_id: account-policy-001
title: 员工账号管理制度
author: IT Department
created_at: 2026-08-01
updated_at: 2026-08-01
tags:
  - security
  - account
  - policy
source_type: pdf
source_path: input/security/account_policy.pdf
version: "1.0"
language: zh-CN
department: IT
---

# 员工账号管理制度

## 1. 总则

企业信息系统账号必须按照统一规范进行管理。

## 2. 离职账号管理

员工离职后，应在规定时间内关闭相关账号。
```

---

## 6.1 Metadata

核心字段：

| 字段 | 说明 |
|---|---|
| document_id | 文档唯一 ID |
| title | 文档标题 |
| author | 文档作者 |
| created_at | 创建时间 |
| tags | 文档标签 |
| source_path | 原始文档路径 |

推荐扩展：

| 字段 | 说明 |
|---|---|
| updated_at | 更新时间 |
| version | 文档版本 |
| source_type | 原始文档类型 |
| language | 文档语言 |
| department | 所属部门 |
| checksum | 原始文件 Hash |
| status | 文档状态 |

---

# 7. OKF 存储设计

## 7.1 存储目录

推荐：

```text
generated/
├── documents/
│   ├── hr/
│   │   ├── employee_handbook.md
│   │   └── leave_policy.md
│   ├── security/
│   │   ├── security_policy.md
│   │   └── account_policy.md
│   └── engineering/
│       └── development_standard.md
└── vector_store/
```

原则：

> OKF 目录结构尽量镜像原始文档目录结构。

这样能够建立：

```text
source_path
    ↓
OKF path
    ↓
document_id
    ↓
chunk_id
    ↓
vector
```

完整的知识追踪链路。

---

# 8. Layer 3 - 向量化层

## 8.1 核心职责

负责：

1. 读取 OKF。
2. 对 Markdown 内容进行结构化 Chunking。
3. 为 Chunk 生成 Embedding。
4. 将向量写入 Vector Store。
5. 保留 Chunk 与 Document 的映射关系。

整体流程：

```text
OKF Document
    ↓
Markdown Parser
    ↓
Heading-aware Chunking
    ↓
Chunks
    ↓
Embedding Provider
    ↓
Vectors
    ↓
FAISS
```

---

# 9. Chunking 设计

## 9.1 Chunking 原则

第一阶段优先采用结构感知的 Chunking：

```text
Document
    ↓
Heading
    ↓
Section
    ↓
Paragraph
    ↓
Token Limit
```

不建议简单按照固定字符数切割整个文档。

原因：

- 标题与正文可能被拆开。
- 条款语义可能被破坏。
- 表格上下文可能丢失。
- 编号关系可能被破坏。
- RAG Context 的可读性下降。

---

## 9.2 初始参数

POC 可以先使用：

```text
chunk_size: 500-1000 tokens
chunk_overlap: 50-150 tokens
top_k: 5
```

最终参数通过测试集进行调整。

---

## 9.3 Chunk Metadata

每个 Chunk 至少保留：

```json
{
  "chunk_id": "account-policy-001-chunk-003",
  "document_id": "account-policy-001",
  "title": "员工账号管理制度",
  "heading": "2. 离职账号管理",
  "content": "员工离职后，应在规定时间内关闭相关账号。",
  "source_path": "input/security/account_policy.pdf"
}
```

---

# 10. Embedding

## 10.1 Provider 抽象

建议不要让业务层直接依赖某个 Embedding 厂商。

定义：

```text
EmbeddingProvider
├── LocalEmbeddingProvider
└── OpenAIEmbeddingProvider
```

这样后续可以替换 Embedding 模型，而不需要修改 Retrieval 层。

---

## 10.2 Local Embedding

第一阶段可以使用：

```text
sentence-transformers
```

优势：

- 本地运行。
- 不依赖外部 API。
- 企业数据无需离开本地。
- 适合 POC。

---

## 10.3 API Embedding

也可以提供：

```text
OpenAI Embedding API
```

优势：

- 集成简单。
- 不需要本地管理模型。
- 适合快速验证效果。

---

# 11. Vector Store

## 11.1 POC 使用 FAISS

第一阶段推荐：

```text
FAISS
```

原因：

- 本地运行简单。
- 不需要独立服务。
- 对 10–20 篇文档足够。
- 便于快速验证 RAG。
- 后续可以替换为 Milvus。

---

## 11.2 Vector Store 抽象

应用层不要直接依赖 FAISS。

建议定义：

```text
VectorStore
├── add()
├── search()
├── delete()
├── rebuild()
└── load()
```

POC 实现：

```text
FAISSVectorStore
```

后续实现：

```text
MilvusVectorStore
```

这样可以降低从 POC 到生产环境的迁移成本。

---

## 11.3 Vector Store 文件

推荐：

```text
generated/vector_store/
├── index.faiss
├── chunks.json
└── metadata.json
```

关系：

```text
FAISS Vector
    ↓
chunk_id
    ↓
chunks.json
    ↓
document_id
    ↓
metadata
```

FAISS 负责：

```text
Similarity Search
```

Metadata 负责：

```text
Document Identity
Title
Heading
Source
Tags
Path
```

---

# 12. Layer 4 - 检索与生成层

## 12.1 RAG Pipeline

第一阶段使用最小 RAG Pipeline：

```text
User Question
    ↓
Query Embedding
    ↓
Vector Search
    ↓
Top-K Chunks
    ↓
Context Builder
    ↓
Prompt
    ↓
LLM
    ↓
Answer + Sources
```

---

## 12.2 Retriever

第一阶段：

```text
Retriever
    ↓
VectorRetriever
    ↓
FAISS
```

后续扩展：

```text
Retriever
├── VectorRetriever
├── KeywordRetriever
└── HybridRetriever
```

---

## 12.3 第二阶段检索演进

企业知识库通常包含：

- 产品编号
- 制度编号
- API 名称
- 项目编号
- 人名
- 缩写
- 专有名词

纯 Vector Search 对精确匹配场景不一定理想。

因此第二阶段建议升级为：

```text
User Query
    ↓
┌─────────────────┐
│                 │
▼                 ▼
Vector Search   BM25 Search
│                 │
└────────┬────────┘
         ↓
      Reranker
         ↓
       Top-K
```

最终形成 Hybrid Search + Reranker。

---

# 13. RAG Context

检索结果需要经过 Context Builder 组装后再交给 LLM。

推荐 Context：

```text
[Document]
Title: 员工账号管理制度
Section: 2. 离职账号管理
Source: input/security/account_policy.pdf

Content:
员工离职后，应在规定时间内关闭相关账号。
```

Context 应包含：

- 文档标题
- Heading
- 正文
- document_id
- source_path
- chunk_id

这样 LLM 可以同时理解内容和来源。

---

# 14. RAG Prompt

第一阶段要求 LLM：

1. 只基于检索到的 Context 回答。
2. 不得编造企业内部规则。
3. 如果知识库没有相关内容，应明确说明。
4. 回答尽量简洁。
5. 返回答案对应的来源。

示例：

```text
System:

你是企业知识库助手。

请严格基于提供的知识库 Context 回答问题。

要求：
1. 不得编造企业内部信息。
2. 如果 Context 中没有足够信息，请明确回答“知识库中没有找到相关信息”。
3. 回答尽量简洁准确。
4. 给出答案对应的文档来源和章节。

Context:
{{context}}

Question:
{{question}}
```

---

# 15. Source Citation

企业知识库必须具备答案溯源能力。

推荐：

```text
员工离职后，应按照账号管理制度的要求关闭相关账号。

来源：
- 员工账号管理制度
- 2. 离职账号管理
```

Source 信息至少保留：

```text
document_id
title
heading
source_path
chunk_id
```

后续可以支持：

- 用户查看原文。
- 答案审计。
- RAG Evaluation。
- 权限校验。
- 文档版本追踪。

---

# 16. Layer 5 - API 服务层

## 16.1 技术栈

推荐：

- FastAPI
- Pydantic
- Uvicorn

## 16.2 API 职责

FastAPI 是知识库对外服务入口。

它不应该直接把所有业务逻辑写在 Router 中。

推荐：

```text
FastAPI
    ↓
API Router
    ↓
Service Layer
    ↓
Repository / Retriever
    ↓
Vector Store / OKF Store
```

---

# 17. API 设计

## 17.1 Health

```http
GET /health
```

返回：

```json
{
  "status": "ok"
}
```

用途：

- 服务健康检查。
- MCP 启动检查。
- 本地调试。

---

## 17.2 List Documents

```http
GET /documents
```

返回：

```json
{
  "documents": [
    {
      "document_id": "account-policy-001",
      "title": "员工账号管理制度",
      "tags": [
        "security",
        "account"
      ]
    }
  ]
}
```

---

## 17.3 Get Document

```http
GET /documents/{document_id}
```

用途：

返回指定 OKF 文档的 Metadata 和全文。

---

## 17.4 Search

```http
GET /search?q=员工离职账号&top_k=5
```

返回：

```json
{
  "query": "员工离职账号",
  "results": [
    {
      "chunk_id": "account-policy-001-chunk-003",
      "document_id": "account-policy-001",
      "title": "员工账号管理制度",
      "heading": "2. 离职账号管理",
      "content": "员工离职后，应在规定时间内关闭相关账号。",
      "score": 0.91,
      "source_path": "input/security/account_policy.pdf"
    }
  ]
}
```

---

## 17.5 RAG Query

```http
POST /query
```

Request：

```json
{
  "question": "员工离职后账号什么时候应该关闭？",
  "top_k": 5
}
```

Response：

```json
{
  "answer": "员工离职后，应在规定时间内关闭相关账号。",
  "sources": [
    {
      "document_id": "account-policy-001",
      "title": "员工账号管理制度",
      "heading": "2. 离职账号管理"
    }
  ]
}
```

---

# 18. API 项目结构

推荐：

```text
src/
├── api/
│   ├── main.py
│   ├── routes_documents.py
│   ├── routes_search.py
│   └── routes_query.py
│
├── services/
│   ├── document_service.py
│   ├── search_service.py
│   └── rag_service.py
│
└── retrieval/
    ├── retriever.py
    └── vector_store.py
```

原则：

> API Layer 负责协议，Service Layer 负责业务，Repository / Vector Store 负责数据访问。

---

# 19. Layer 6 - MCP 接口层

## 19.1 核心职责

MCP 层负责把知识库能力暴露给 Kiro Agent。

MCP 不负责重新实现：

- 文档解析。
- Chunking。
- Embedding。
- Vector Search。
- RAG 核心逻辑。

推荐：

```text
Kiro Agent
    ↓
MCP Server
    ↓
FastAPI
    ↓
Knowledge Service
```

MCP 是 Agent 接入协议层，而不是新的知识库业务层。

---

# 20. MCP Tools

第一阶段推荐三个 Tool。

## 20.1 list_documents

用途：

列出知识库文档。

```text
list_documents(
    keyword?,
    tag?,
    department?
)
```

---

## 20.2 query_documents

用途：

根据自然语言问题检索知识片段。

```text
query_documents(
    query,
    top_k?
)
```

返回：

```json
{
  "results": [
    {
      "document_id": "account-policy-001",
      "title": "员工账号管理制度",
      "heading": "2. 离职账号管理",
      "content": "员工离职后，应在规定时间内关闭相关账号。",
      "score": 0.91
    }
  ]
}
```

---

## 20.3 get_document

用途：

获取指定文档全文。

```text
get_document(
    document_id
)
```

返回：

```json
{
  "document_id": "account-policy-001",
  "title": "员工账号管理制度",
  "metadata": {
    "author": "IT Department",
    "tags": [
      "security",
      "account"
    ]
  },
  "content": "# 员工账号管理制度\n..."
}
```

---

# 21. Layer 7 - Kiro Agent 集成层

## 21.1 核心职责

Kiro Agent 是最终用户交互入口。

Agent 负责：

1. 理解用户问题。
2. 判断是否需要查询企业知识库。
3. 调用 MCP Tool。
4. 获取相关知识。
5. 基于知识上下文生成最终答案。
6. 输出来源。

---

# 22. 最小闭环

典型流程：

```text
User
  ↓
Kiro Agent
  ↓
query_documents()
  ↓
MCP Server
  ↓
FastAPI /search
  ↓
Retriever
  ↓
FAISS
  ↓
Relevant Chunks
  ↓
MCP Response
  ↓
Kiro Agent
  ↓
LLM
  ↓
Answer + Sources
```

如果需要完整文档：

```text
Kiro Agent
  ↓
query_documents()
  ↓
发现相关文档
  ↓
get_document()
  ↓
获取完整 OKF
  ↓
LLM
  ↓
Final Answer
```

---

# 23. 第一阶段实施计划

## Phase 1.1 - 文档转换

目标：

将 10–20 篇真实企业文档转换成 OKF。

输入：

```text
PDF
Word
Confluence HTML
TXT
```

输出：

```text
generated/documents/
```

主要任务：

- 实现 PDF Parser。
- 实现 DOCX Parser。
- 实现 HTML Parser。
- 实现 TXT Parser。
- 实现统一 Metadata。
- 保留 Heading 层级。
- 保留 source_path。
- 生成 Markdown + YAML。

验收：

- 10–20 篇文档全部成功转换。
- 没有严重乱码。
- 标题层级基本正确。
- Metadata 完整。
- 可以从 OKF 找回原始文件路径。

---

# 24. Phase 1.2 - 向量化与检索

目标：

将 OKF 文档建立向量索引。

流程：

```text
OKF
 ↓
Chunking
 ↓
Embedding
 ↓
FAISS
```

主要任务：

- 实现 Chunking。
- 实现 EmbeddingProvider。
- 实现 FAISSVectorStore。
- 建立 chunk_id → document_id 映射。
- 实现 Top-K Search。

验收：

准备至少 20 个测试问题。

检查：

- Top-1 是否命中正确知识。
- Top-5 是否包含正确知识。
- 是否出现大量无关结果。
- Chunk 是否包含完整语义。

---

# 25. Phase 1.3 - RAG Pipeline

目标：

在向量检索基础上完成问答。

流程：

```text
Question
 ↓
Search
 ↓
Top-K Context
 ↓
Prompt
 ↓
LLM
 ↓
Answer + Sources
```

主要任务：

- 实现 RAG Pipeline。
- 实现 Context Builder。
- 实现 Prompt。
- 增加 Source Citation。
- 增加“不知道”策略。

重点测试：

1. 直接事实问题。
2. 多文档问题。
3. 模糊问题。
4. 知识库没有答案的问题。
5. 相似文档干扰问题。
6. 跨章节问题。

---

# 26. Phase 1.4 - FastAPI

目标：

通过 API 暴露知识库能力。

最低接口：

```text
GET  /health
GET  /documents
GET  /documents/{document_id}
GET  /search
POST /query
```

验收：

```text
curl /health
curl /documents
curl /search?q=...
curl /documents/{id}
POST /query
```

均可以正常工作。

---

# 27. Phase 1.5 - MCP

目标：

将 FastAPI 能力封装成 MCP Tools。

最小 Tools：

```text
list_documents
query_documents
get_document
```

验收：

- MCP Server 能够启动。
- Kiro 能够发现 MCP Tools。
- Kiro 能够调用 query_documents。
- MCP 能够返回检索结果。
- Kiro 能够基于结果生成答案。

---

# 28. Phase 1.6 - 最小闭环

最终验收：

```text
Kiro CLI
   ↓
用户自然语言问题
   ↓
Kiro Agent
   ↓
MCP Tool Call
   ↓
Knowledge Base API
   ↓
FAISS Retrieval
   ↓
Relevant Chunks
   ↓
Agent LLM
   ↓
Answer + Source
```

示例：

用户输入：

```text
员工离职后账号什么时候应该关闭？
```

Agent：

```text
调用 query_documents()
```

知识库：

```text
返回：
员工账号管理制度
2. 离职账号管理
相关 Chunk
```

Agent：

```text
基于 Chunk 生成最终答案
```

最终：

```text
员工离职后，应按照员工账号管理制度中的规定关闭相关账号。

来源：
- 员工账号管理制度
- 2. 离职账号管理
```

---

# 29. 第一阶段推荐技术栈

| 层 | 技术 | 用途 |
|---|---|---|
| Language | Python | 主开发语言 |
| PDF | PyMuPDF | PDF 解析 |
| Word | python-docx | DOCX 解析 |
| HTML | BeautifulSoup | HTML 解析 |
| Format | Markdown + YAML | OKF |
| Chunking | LangChain / 自实现 | 文档分块 |
| Embedding | sentence-transformers | 本地 Embedding |
| Embedding | OpenAI Embedding API | API Embedding，可选 |
| Vector DB | FAISS | POC 向量检索 |
| RAG | LangChain / LlamaIndex | RAG Pipeline |
| LLM | OpenAI / 企业内部 LLM | 答案生成 |
| API | FastAPI | HTTP API |
| Server | Uvicorn | FastAPI Runtime |
| MCP | MCP Server | Agent Tool |
| Agent | Kiro Agent | 最终用户入口 |

---

# 30. 推荐项目目录

```text
enterprise-kb-poc/
│
├── config/
│   └── doc_to_okf_config.yaml
│
├── input/
│   ├── pdf/
│   ├── word/
│   ├── confluence/
│   └── txt/
│
├── generated/
│   ├── documents/
│   │   ├── hr/
│   │   ├── security/
│   │   └── engineering/
│   │
│   └── vector_store/
│       ├── index.faiss
│       ├── chunks.json
│       └── metadata.json
│
├── scripts/
│   ├── import_raw_doc_to_okf.py
│   ├── build_index.py
│   └── test_rag.py
│
├── src/
│   ├── ingestion/
│   │   ├── pdf_parser.py
│   │   ├── word_parser.py
│   │   ├── html_parser.py
│   │   ├── txt_parser.py
│   │   └── okf_writer.py
│   │
│   ├── embedding/
│   │   ├── base.py
│   │   ├── local.py
│   │   └── openai.py
│   │
│   ├── retrieval/
│   │   ├── vector_store.py
│   │   ├── faiss_store.py
│   │   └── retriever.py
│   │
│   ├── rag/
│   │   ├── pipeline.py
│   │   ├── prompt.py
│   │   └── context.py
│   │
│   ├── services/
│   │   ├── document_service.py
│   │   ├── search_service.py
│   │   └── rag_service.py
│   │
│   ├── api/
│   │   ├── main.py
│   │   ├── routes_documents.py
│   │   ├── routes_search.py
│   │   └── routes_query.py
│   │
│   └── mcp/
│       └── server.py
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_chunking.py
│   ├── test_retrieval.py
│   ├── test_rag.py
│   └── test_api.py
│
├── requirements.txt
└── README.md
```

---

# 31. 核心模块职责

| 模块 | 职责 |
|---|---|
| ingestion | 原始文档解析与 OKF 转换 |
| embedding | Embedding Provider |
| retrieval | Vector Store 与 Retriever |
| rag | RAG Pipeline |
| services | 知识库业务逻辑 |
| api | HTTP API |
| mcp | Agent Tool 接口 |
| scripts | 数据导入、索引构建、测试 |
| tests | 自动化测试 |

---

# 32. 核心接口抽象

为了保证后续服务化和组件替换，建议在 POC 阶段就做以下抽象。

## 32.1 DocumentLoader

```text
DocumentLoader
├── PDFLoader
├── DOCXLoader
├── HTMLLoader
└── TXTLoader
```

---

## 32.2 EmbeddingProvider

```text
EmbeddingProvider
├── LocalEmbeddingProvider
└── OpenAIEmbeddingProvider
```

核心接口：

```text
embed(text)
embed_batch(texts)
```

---

## 32.3 VectorStore

```text
VectorStore
├── FAISSVectorStore
└── MilvusVectorStore
```

核心接口：

```text
add()
search()
delete()
rebuild()
load()
```

---

## 32.4 Retriever

```text
Retriever
├── VectorRetriever
├── KeywordRetriever
└── HybridRetriever
```

核心接口：

```text
retrieve(query, top_k)
```

---

## 32.5 LLM Provider

建议进一步抽象：

```text
LLMProvider
├── OpenAILLM
└── EnterpriseLLM
```

这样未来切换企业内部模型时不需要修改 RAG Pipeline。

---

# 33. 数据流设计

## 33.1 Ingestion Data Flow

```text
Raw File
   ↓
Parser
   ↓
Normalized Document
   ↓
Metadata
   ↓
OKF
   ↓
generated/documents/
```

---

## 33.2 Indexing Data Flow

```text
OKF
   ↓
Markdown Parser
   ↓
Chunking
   ↓
Chunk Metadata
   ↓
Embedding
   ↓
FAISS
```

---

## 33.3 Search Data Flow

```text
Query
   ↓
Query Embedding
   ↓
FAISS Search
   ↓
Top-K chunk_id
   ↓
Chunk Metadata
   ↓
Search Results
```

---

## 33.4 RAG Data Flow

```text
Question
   ↓
Retriever
   ↓
Relevant Chunks
   ↓
Context Builder
   ↓
Prompt
   ↓
LLM
   ↓
Answer
   +
Sources
```

---

## 33.5 Agent Data Flow

```text
User
   ↓
Kiro Agent
   ↓
MCP Tool
   ↓
FastAPI
   ↓
Knowledge Service
   ↓
Retriever
   ↓
Vector Store
   ↓
Relevant Knowledge
   ↓
MCP Response
   ↓
Kiro Agent
   ↓
LLM
   ↓
Final Answer
```

---

# 34. 关键设计原则

## 34.1 OKF 是知识中间层

原始格式：

```text
PDF / Word / HTML / TXT
```

统一转换：

```text
OKF
```

后续：

```text
OKF
 ↓
Chunking
 ↓
Embedding
 ↓
Search
 ↓
RAG
```

这样可以彻底解耦文档解析和 RAG。

---

## 34.2 Metadata 与 Vector 分离

Vector Store 负责：

```text
Similarity Search
```

Metadata Store / OKF 负责：

```text
Document Identity
Title
Source
Heading
Tags
Version
Path
```

不要把所有业务 Metadata 与 Vector Search 逻辑耦合在一起。

---

## 34.3 Retriever 与 LLM 解耦

必须能够独立调用：

```text
/search
```

验证：

```text
“检索是否正确？”
```

再通过：

```text
/query
```

验证：

```text
“LLM 是否能够正确回答？”
```

这样可以区分：

- Retrieval Error
- Context Error
- Generation Error

---

## 34.4 MCP 与 Knowledge Service 解耦

MCP 不是知识库业务层。

正确结构：

```text
Kiro
 ↓
MCP
 ↓
FastAPI
 ↓
Knowledge Service
 ↓
Retriever / RAG
```

而不是：

```text
Kiro
 ↓
MCP
 ↓
直接操作 FAISS
```

这样未来即使 Kiro/MCP 被替换，Knowledge Service 仍然可以服务其他客户端。

---

## 34.5 POC 优先 FAISS

第一阶段：

```text
FAISS
```

第二阶段：

```text
Milvus
```

迁移过程中：

```text
Retriever
   ↓
VectorStore Interface
   ↓
FAISS / Milvus
```

上层业务不应该感知具体 Vector DB。

---

## 34.6 从第一阶段开始保留 Source Citation

企业知识库的核心要求不仅是：

```text
Answer
```

还应该是：

```text
Answer
+
Source
```

因为企业用户需要知道：

- 答案来自哪份文档。
- 来自哪个章节。
- 使用了哪个 Chunk。
- 是否可以回溯原始文档。

---

# 35. POC 到生产环境演进路线

## Phase 1 - Local POC

```text
Local Files
    ↓
OKF
    ↓
FAISS
    ↓
FastAPI
    ↓
MCP
    ↓
Kiro
```

特点：

- 单机。
- 小规模。
- 手动导入。
- 本地向量库。
- 最小服务化。

---

## Phase 2 - Service-oriented

```text
                 ┌── PostgreSQL
                 │
Raw Documents → Ingestion Service
                 │
                 ├── Object Storage
                 │
                 └── OKF
                       ↓
                  Embedding
                       ↓
                    Milvus
                       ↓
                 Search Service
                       ↓
                   RAG Service
                       ↓
                  FastAPI API
                       ↓
                  MCP Gateway
```

新增：

- PostgreSQL
- Object Storage
- Milvus
- Redis
- 异步任务队列
- Document Service
- Search Service
- RAG Service

---

# 36. Phase 3 - Enterprise Production

生产环境进一步增加：

## 数据与存储

- Object Storage
- PostgreSQL
- Milvus
- Redis

## 异步处理

- Kafka / RabbitMQ / Celery
- 增量索引
- 文档更新检测
- 删除与重建 Index

## 检索能力

- Hybrid Search
- BM25
- Vector Search
- Reranker
- Metadata Filter

## 企业能力

- SSO
- IAM
- RBAC
- ACL
- 多租户
- 审计日志

## AI 能力

- Model Gateway
- Prompt Management
- RAG Evaluation
- LLM Observability
- Feedback Loop
- Agent Gateway

---

# 37. 第一阶段不建议引入的组件

为了快速完成 POC，第一阶段暂不建议引入：

- Kubernetes
- Kafka
- Redis
- Milvus
- PostgreSQL
- 分布式任务系统
- 微服务拆分
- 多租户
- RBAC
- 复杂权限系统
- 大规模 Agent Orchestration

原因：

第一阶段需要验证的是：

```text
Knowledge Quality
+
Retrieval Quality
+
RAG Quality
+
Agent Integration
```

而不是基础设施规模。

---

# 38. 第一阶段验收标准

## 38.1 文档转换

- [ ] 10–20 篇真实文档能够成功导入。
- [ ] PDF 转换正常。
- [ ] Word 转换正常。
- [ ] HTML 转换正常。
- [ ] TXT 转换正常。
- [ ] Heading 层级基本正确。
- [ ] YAML Metadata 完整。
- [ ] source_path 可追溯。
- [ ] 原始目录结构能够镜像到 generated。

## 38.2 向量检索

- [ ] OKF 能够正确 Chunk。
- [ ] Embedding 能够正常生成。
- [ ] FAISS Index 能够创建。
- [ ] Query 能够返回 Top-K。
- [ ] 返回结果包含 document_id。
- [ ] 返回结果包含 source_path。
- [ ] 返回结果包含 heading。
- [ ] Top-K 结果能够命中测试知识。

## 38.3 RAG

- [ ] 能够基于检索结果回答问题。
- [ ] 能够输出 Source。
- [ ] 知识库没有答案时不会明显编造。
- [ ] 支持跨 Chunk 问题。
- [ ] 支持跨文档问题。

## 38.4 API

- [ ] /health 正常。
- [ ] /documents 正常。
- [ ] /documents/{id} 正常。
- [ ] /search 正常。
- [ ] /query 正常。

## 38.5 MCP

- [ ] MCP Server 能启动。
- [ ] Kiro 能发现 MCP Tools。
- [ ] Kiro 能调用 query_documents。
- [ ] Kiro 能调用 get_document。
- [ ] Kiro 能基于知识库结果生成回答。

## 38.6 最终闭环

必须能够完成：

```text
Kiro CLI
  ↓
用户提问
  ↓
Agent
  ↓
MCP
  ↓
FastAPI
  ↓
FAISS
  ↓
Relevant Chunks
  ↓
Agent LLM
  ↓
Answer + Source
```

---

# 39. 最终推荐架构

第一阶段推荐保持以下最小技术组合：

```text
Python
  │
  ├── PyMuPDF
  ├── python-docx
  ├── BeautifulSoup
  │
  ├── Markdown + YAML
  │
  ├── sentence-transformers
  │
  ├── FAISS
  │
  ├── LangChain / LlamaIndex
  │
  ├── FastAPI
  │
  ├── MCP Server
  │
  └── Kiro Agent
```

核心链路：

```text
企业原始文档
      ↓
Document Ingestion
      ↓
OKF
      ↓
Chunking
      ↓
Embedding
      ↓
FAISS
      ↓
Retriever
      ↓
RAG
      ↓
FastAPI
      ↓
MCP
      ↓
Kiro Agent
      ↓
Answer + Sources
```

---

# 40. 架构总结

整个 POC 的核心不是堆叠大量基础设施，而是建立清晰的知识处理链路：

```text
原始文档
    ↓
统一知识格式 OKF
    ↓
结构化 Chunk
    ↓
Embedding
    ↓
Vector Search
    ↓
RAG
    ↓
Knowledge API
    ↓
MCP
    ↓
Agent
```

其中：

- OKF 解决“知识如何统一表示”。
- Chunking 解决“知识如何切分”。
- Embedding 解决“知识如何进行语义表示”。
- FAISS 解决“知识如何快速召回”。
- RAG 解决“如何基于企业知识生成答案”。
- FastAPI 解决“如何服务化”。
- MCP 解决“如何让 Agent 使用知识库”。
- Kiro Agent 解决“如何形成最终用户交互闭环”。

第一阶段最重要的成果是：

> 在本地使用 10–20 篇真实企业文档，稳定跑通“文档 → OKF → Vector → Search → RAG → FastAPI → MCP → Kiro Agent → Answer + Source”的最小闭环。

后续所有生产化能力，例如 Milvus、PostgreSQL、Object Storage、Redis、Hybrid Search、Reranker、RBAC、ACL、异步任务和多租户，都应该建立在这个清晰的 POC 分层之上，而不是在第一阶段提前引入。
