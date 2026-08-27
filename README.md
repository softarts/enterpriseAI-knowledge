# 企业知识库（Enterprise Knowledge Base）

本项目通过 MCP 把 Kiro 与企业知识库的检索能力打通，形成最小闭环：

```
用户问题
  ↓
Kiro
  ↓
MCP（enterprise-kb 服务器）
  ↓
现有的 Embedding / Retrieval 能力
  ↓
返回若干相关 Context
  ↓
Kiro（LLM）
  ↓
最终答案 + 来源引用
```

MCP 只负责返回检索到的 Context，最终答案由 Kiro（LLM）根据这些 Context 自行合成。

---

## 通过 MCP 查询的完整示例

下面用一个真实问题演示整个流程：

> **What mandatory fields must be included in a compliance evidence bundle?**
> （合规证据包必须包含哪些字段？）

### 1. 启动 MCP Server，并在 Kiro 中输入查询

先启动统一服务（同时拉起 REST API :8000 与 MCP Server :8001）：

```bash
python -m doc_service.mcp_main
```

- MCP 服务器地址：`http://localhost:8001/mcp`
- Kiro 侧的连接配置在 `.kiro/settings/mcp.json` 里的 `enterprise-kb` 条目。
- 如果端口 8000 / 8001 已被占用，说明实例已经在运行，无需重复启动
  （`mcp_main.py` 会做端口预检并给出明确提示后退出，而不是抛出一大段堆栈）。

然后在 Kiro 窗口中输入（触发 `enterprise-knowledge` 技能，强制走 MCP）：

```
use enterprise-knowledge mcp: What mandatory fields must be included in a compliance evidence bundle?
```

Kiro 会调用 `enterprise-kb` 这个 MCP 服务器的工具
`search_knowledge(query, top_k=5)`，而**不是**直接调用本地函数或 REST 接口。

### 2. MCP 内部对应调用的函数（文件与行号）

一次 `search_knowledge` 调用在服务端的完整链路如下（自上而下）：

| 步骤 | 函数 | 文件:行号 |
|---|---|---|
| MCP 工具入口 | `search_knowledge(query, top_k)` | `doc_service/mcp/server.py:114` |
| 选择 embedding 后端的服务实例 | `get_embedding_knowledge_service()` | `doc_service/api/dependencies.py:46` |
| 服务层统一检索入口 | `KnowledgeService.search(query, top_k)` | `doc_service/services/knowledge_service.py:80` |
| Retriever 协议 → embedding 实现 | `EmbeddingRetriever.retrieve(query, top_k)` | `doc_service/retrieval/embedding_retriever.py:43` |
| 把查询编码为向量 | `LocalEmbedder.embed_query(query)` | `embedding_service/embedder.py:38` |
| 加载已持久化的 embedding | `load_all_embeddings(embedding_dir)` | `embedding_service/storage.py:65` |
| 余弦相似度取 Top-K | `search_by_similarity(query_vector, chunks, top_k)` | `embedding_service/search.py:46` |

调用关系（一句话概括）：

```
search_knowledge (server.py:114)
  → get_embedding_knowledge_service (dependencies.py:46)
    → KnowledgeService.search (knowledge_service.py:80)
      → EmbeddingRetriever.retrieve (embedding_retriever.py:43)
        → LocalEmbedder.embed_query (embedder.py:38)
        → load_all_embeddings (storage.py:65)
        → search_by_similarity (search.py:46)
```

> 设计要点：MCP 接口与检索后端是**解耦**的。`Retriever` 协议
> （`doc_service/retrieval/retriever.py:33`）是唯一的接缝，未来换成向量数据库
> （如 Chroma）只需新增一个实现同样协议的类，`search_knowledge` 的调用方式不变。

### 3. Embedding 检索得到并 assemble 后发给 Kiro 的原始内容

MCP 工具返回的是一段 JSON（Context，不含最终答案）。对上面的问题、`top_k=3`
时，实际返回内容如下（这就是“机器发给 Kiro 的原始内容”）：

```json
{
  "query": "What mandatory fields must be included in a compliance evidence bundle?",
  "top_k": 3,
  "results": [
    {
      "rank": 1,
      "score": 0.589,
      "document_id": "confluence-people-ops-onboarding-dsid-fe4f3a98cd9642afa7f9a150de313c5c-authn-audit-evidence-correlation-playbook-2028",
      "heading": "Acceptance criteria for compliance reviewers",
      "chunk_id": "confluence-people-ops-onboarding-dsid-fe4f3a98cd9642afa7f9a150de313c5c-authn-audit-evidence-correlation-playbook-2028-chunk-014",
      "title": "Authentication + Audit Evidence Correlation Playbook",
      "source_path": "confluence/people-ops/onboarding/dsid_fe4f3a98cd9642afa7f9a150de313c5c__authn-audit-evidence-correlation-playbook-2028.txt",
      "text": "- Evidence package contains: authN/authZ events, resource-access logs, policy snapshot (versioned), deployment provenance, signed manifest.\n- All items are checksum-verified and the manifest signature validates against a recognized KMS key.\n- Residency constraints are explicit and no evidence artifacts violate the stated residency policy."
    },
    {
      "rank": 2,
      "score": 0.5286,
      "document_id": "confluence-people-ops-onboarding-dsid-fe4f3a98cd9642afa7f9a150de313c5c-authn-audit-evidence-correlation-playbook-2028",
      "heading": "Key definitions",
      "chunk_id": "confluence-people-ops-onboarding-dsid-fe4f3a98cd9642afa7f9a150de313c5c-authn-audit-evidence-correlation-playbook-2028-chunk-002",
      "title": "Authentication + Audit Evidence Correlation Playbook",
      "source_path": "confluence/people-ops/onboarding/dsid_fe4f3a98cd9642afa7f9a150de313c5c__authn-audit-evidence-correlation-playbook-2028.txt",
      "text": "- AuthN event: identity verification occurrences (e.g., OAuth token issuance, SAML assertion, service identity key rotation).\n- AuthZ event: authorization decision or policy evaluation (e.g., ALLOW/DENY, role check outcome).\n- Evidence bundle: time-bounded set of log slices, policy snapshots, configuration hashes, and a signed manifest.\n- Residency marker: metadata attribute associated with a request or object that indicates geographic and legal residency constraints."
    },
    {
      "rank": 3,
      "score": 0.5177,
      "document_id": "confluence-people-ops-onboarding-dsid-fe4f3a98cd9642afa7f9a150de313c5c-authn-audit-evidence-correlation-playbook-2028",
      "heading": "Risk exceptions and approval workflow",
      "chunk_id": "confluence-people-ops-onboarding-dsid-fe4f3a98cd9642afa7f9a150de313c5c-authn-audit-evidence-correlation-playbook-2028-chunk-012",
      "title": "Authentication + Audit Evidence Correlation Playbook",
      "source_path": "confluence/people-ops/onboarding/dsid_fe4f3a98cd9642afa7f9a150de313c5c__authn-audit-evidence-correlation-playbook-2028.txt",
      "text": "- Exceptions ... must be requested using the Exception Request form and include compensating controls.\n- Exception approval path: Requestor -> Security reviewer -> Compliance approver -> Risk committee (for >90 days or production exceptions).\n- Approved exceptions are recorded in the Exception Register with: id, justification, owner, expiration date, compensating controls, and link to evidence artifacts if any."
    }
  ]
}
```

返回内容中每个 chunk 至少包含：`rank`（排名）、`score`（相似度分数）、
`document_id`、`heading`、`chunk_id`、`title`、`source_path`、`text`（原文，逐字不改写）。

Kiro 拿到这些 Context 之后，只依据其中的信息合成最终答案，并按 `[SOURCE <rank>]`
标注来源；不使用任何外部知识。

### 4. Embedding retrieval 是怎么查询的（过程简述）

整体是一个标准的“稠密向量语义检索”，过程如下：

1. **离线阶段（事先完成）**：OKF 文档被切成 chunk，用本地 SBERT 模型
   （`all-MiniLM-L6-v2`，384 维）逐个编码成向量，并连同元数据持久化到
   `embedding/` 目录下的 JSON 文件中（本项目当前共 43 个 chunk）。
2. **加载**：查询时把 `embedding/` 下所有已持久化的 chunk 向量读入内存。
3. **查询编码**：用**同一个** SBERT 模型把用户的问题编码成一个查询向量，
   并做归一化处理。
4. **相似度计算**：把查询向量与每个 chunk 向量做余弦相似度比较（向量已归一化，
   等价于点积），得到每个 chunk 的相关性分数。
5. **取 Top-K 排序**：按分数从高到低排序，取前 `top_k` 个，赋予 `rank`，
   并映射为统一的结果结构（含 `score`、`heading`、`text` 等）返回。

这一步只做“检索/召回”，不做重排、不做关键词/混合检索、不生成答案——
生成答案是 Kiro（LLM）在收到 Context 之后独立完成的，检索与生成保持解耦。

---

## Chroma / Vector DB（第一阶段）

上面的 embedding 检索是把所有向量读进内存后逐个算相似度。第一阶段我们额外引入
**Chroma** 作为持久化向量库，用来直观演示完整链路：

```
OKF 文档（generated/*.yaml）
  ↓  切块 + SBERT 编码（all-MiniLM-L6-v2, 384 维, 归一化）
Embedding（EmbeddedChunk）
  ↓  --vector-db 开关：upsert 写入
Chroma 持久化库（vector_db/, collection = okf_chunks, 余弦距离）
  ↓  查询：把 query 用同一模型编码成向量
Vector Search（Top-K 最近邻，返回 distance + text + metadata）
```

本阶段**只**验证 `Embedding → Chroma → Vector Search`，不含 BM25、reranker、
hybrid search、MCP、LLM、context assembly。默认行为不变：不加 `--vector-db` 时
不会导入 chromadb，也不会写 `vector_db/`。

### 1. 写入示例（把 embedding 写进 Chroma）

```bash
# 默认行为不变，仍写 embedding/*.json；额外把向量 upsert 到 vector_db/
python embedding_service/main_import.py --vector-db
```

实际输出（节选）：

```
Successfully embedded [...authn-audit-evidence-correlation-playbook-2028] (19 chunks) -> ...json
  -> upserted 19 chunks into Chroma vector store
OKF embedding batch completed: 8 succeeded, 0 failed out of 8 files.
Vector DB: collection 'okf_chunks' now holds 43 records at .../vector_db
```

写入链路对应代码（文件:行号）：

| 步骤 | 函数 | 文件:行号 |
|---|---|---|
| 导入开关 `--vector-db` | argparse 定义 | `embedding_service/main_import.py:185` |
| 启用时打开 Chroma 库 | `if args.vector_db: ChromaStore(...)` | `embedding_service/main_import.py:230` |
| 每个文档 upsert 向量 | `process_okf_document(..., vector_store=...)` | `embedding_service/main_import.py:93` |
| 批量 upsert 实现 | `ChromaStore.add_embedded_chunks(chunks)` | `vector_service/chroma_store.py:108` |

`add_embedded_chunks` 用 `chunk_id` 作主键（幂等 upsert）：`content` 存为
document，`document_id / title / heading / source_path` 存为 metadata，
预先算好的向量存为 embedding。

### 2. 确认数据已写入（stats）

```bash
python -m vector_service.cli stats
```

实际输出：

```
CHROMA COLLECTION STATS
  collection_name:     okf_chunks
  count (records):     43
  persist_dir:         .../vector_db
  distance_space:      cosine
  embedding_dimension: 384
```

对应代码：`ChromaStore.stats()` 在 `vector_service/chroma_store.py:196`，
CLI 子命令 `cmd_stats` 在 `vector_service/cli.py:84`。

### 3. 查询示例（自然语言 → 向量 → Top-K）

```bash
python -m vector_service.cli search "What mandatory fields must be included in a compliance evidence bundle?" --top-k 3
```

实际输出（节选，`distance` 为余弦距离，越小越相关）：

```
QUERY: What mandatory fields must be included in a compliance evidence bundle?
Collection: okf_chunks  (count=43, space=cosine)

[1] distance=0.4110
    chunk_id:    ...authn-audit-evidence-correlation-playbook-2028-chunk-014
    document_id: ...authn-audit-evidence-correlation-playbook-2028
    title:       Authentication + Audit Evidence Correlation Playbook
    heading:     Acceptance criteria for compliance reviewers
    source_path: confluence/people-ops/onboarding/...playbook-2028.txt
    text:
      - Evidence package contains: authN/authZ events, resource-access logs, policy snapshot (versioned), deployment provenance, signed manifest.
      ...
[2] distance=0.4714  heading: Key definitions
[3] distance=0.4823  heading: Risk exceptions and approval workflow
```

查询链路对应代码（文件:行号）：

| 步骤 | 函数 | 文件:行号 |
|---|---|---|
| CLI `search` 子命令 | `cmd_search(args)` | `vector_service/cli.py:40` |
| 把 query 编码为向量 | `LocalEmbedder.embed_query(query)` | `embedding_service/embedder.py:38` |
| Chroma Top-K 查询 | `ChromaStore.query(query_vector, top_k)` | `vector_service/chroma_store.py:146` |

> 说明：`distance`（余弦距离）与前文 embedding 检索的 `score`（余弦相似度）互为
> 补数，`distance ≈ 1 - score`（例如 Top-1 `0.4110 ≈ 1 - 0.589`），二者返回的
> 顺序一致，说明 Chroma 检索与内存检索结果吻合。

> 设计要点：`ChromaStore` 与其它模块解耦、不自己做文本编码（调用方传入向量），
> 因此未来可被一个查询 Chroma 的 MCP 工具直接复用，无需改动。~~**本阶段不修改现有 MCP。**~~
> **已在下一节实现 MCP → Chroma 集成。**

---

## MCP + Chroma Search

在上一节实现了 CLI 级别的 Chroma 查询之后，本节打通了 **Kiro → MCP → Chroma DB**
的完整链路，使 Kiro 可以直接通过 MCP 工具 `search_chroma` 从 Chroma 向量库检索。

### 整体流程图

```
用户问题
  ↓
Kiro
  ↓  调用 MCP 工具 search_chroma(query, top_k)
MCP Server（enterprise-kb, :8001/mcp）
  ↓  get_local_embedder().embed_query(query)
Embedding（SBERT all-MiniLM-L6-v2, 384 维, 归一化）
  ↓  get_chroma_store().query(query_vector, top_k)
Chroma DB（vector_db/, collection=okf_chunks, cosine）
  ↓  Top-K nearest neighbors
Search Results（rank, distance, metadata, text）
  ↓  格式化为 JSON
MCP Response
  ↓
Kiro（拿到 Context 后自行合成答案）
```

### MCP API 是哪个接口

工具名：`search_chroma`，定义在 `doc_service/mcp/server.py:176`。

参数：
- `query`（str）— 自然语言问题
- `top_k`（int, 默认 5）— 返回条数

### 内部调用链路（文件:行号）

| 步骤 | 说明 | 文件:行号 |
|---|---|---|
| 1 | MCP 工具入口 | `doc_service/mcp/server.py:176` (`search_chroma`) |
| 2 | 获取 LocalEmbedder 单例 | `doc_service/api/dependencies.py:89` (`get_local_embedder`) |
| 3 | 把 query 编码为向量 | `embedding_service/embedder.py:38` (`embed_query`) |
| 4 | 获取 ChromaStore 单例 | `doc_service/api/dependencies.py:76` (`get_chroma_store`) |
| 5 | 从 Chroma 查 Top-K | `vector_service/chroma_store.py:146` (`ChromaStore.query`) |
| 6 | 格式化结果为 JSON | `doc_service/mcp/server.py:217` (列表推导) |

调用关系一句话：

```
search_chroma (server.py:176)
  → get_local_embedder (dependencies.py:89)
    → LocalEmbedder.embed_query (embedder.py:38)
  → get_chroma_store (dependencies.py:76)
    → ChromaStore.query (chroma_store.py:146)
      → chromadb PersistentClient @ vector_db/
  → json.dumps → MCP response
```

### 如何接收 query 并生成 embedding

1. Kiro 通过 MCP 传入 `query`（字符串）和 `top_k`。
2. `get_local_embedder()` 返回一个缓存的 `LocalEmbedder` 实例（SBERT
   `all-MiniLM-L6-v2`，384 维，L2 归一化）。
3. `embedder.embed_query(query)` 把文本编码为 384 维浮点向量，与导入时使用的
   模型**完全一致**，确保查询向量与库中向量处于同一空间。

### 如何从 Chroma DB 查询

1. `get_chroma_store()` 返回一个缓存的 `ChromaStore` 实例（Chroma PersistentClient
   指向 `vector_db/`，collection `okf_chunks`，距离度量 = cosine）。
2. `store.query(query_vector, top_k)` 调用 Chroma 的 `collection.query()`，
   传入 `query_embeddings=[query_vector]`，要求返回 `documents + metadatas + distances`。
3. Chroma 内部用 HNSW 索引执行近似最近邻搜索，返回余弦距离最小的 Top-K 条记录。

### 如何组合返回结果

对 Chroma 返回的原始列表（`ids, documents, metadatas, distances`）逐条映射为：

```json
{
  "rank": 1,
  "distance": 0.411,
  "score": 0.589,
  "document_id": "...",
  "heading": "...",
  "chunk_id": "...",
  "title": "...",
  "source_path": "...",
  "text": "..."
}
```

- `rank` = 1-indexed 排名（distance 升序）。
- `distance` = Chroma 返回的余弦距离（越小越相关）。
- `score` = `1 - distance`（余弦相似度，方便与 `search_knowledge` 对比）。
- `text` = chunk 原文（Chroma document 字段，未做任何修改）。
- 其余字段 = Chroma metadata。

最终包裹为 envelope：`{ query, top_k, backend: "chroma", results: [...] }`。

### 最终返回给 Kiro 的数据结构

```json
{
  "query": "What mandatory fields must be included in a compliance evidence bundle?",
  "top_k": 3,
  "backend": "chroma",
  "results": [
    {
      "rank": 1,
      "distance": 0.411,
      "score": 0.589,
      "document_id": "confluence-people-ops-onboarding-dsid-...playbook-2028",
      "heading": "Acceptance criteria for compliance reviewers",
      "chunk_id": "...playbook-2028-chunk-014",
      "title": "Authentication + Audit Evidence Correlation Playbook",
      "source_path": "confluence/people-ops/onboarding/...playbook-2028.txt",
      "text": "- Evidence package contains: authN/authZ events, ..."
    },
    { "rank": 2, "distance": 0.4714, "score": 0.5286, "heading": "Key definitions", "..." : "..." },
    { "rank": 3, "distance": 0.4823, "score": 0.5177, "heading": "Risk exceptions and approval workflow", "..." : "..." }
  ]
}
```

### 涉及的文件汇总

| 文件 | 相关行 | 职责 |
|---|---|---|
| `doc_service/mcp/server.py` | 176-230 | `search_chroma` 工具定义 + 结果格式化 |
| `doc_service/api/dependencies.py` | 76-98 | `get_chroma_store()` 和 `get_local_embedder()` 单例 |
| `embedding_service/embedder.py` | 38-48 | `LocalEmbedder.embed_query()` — 编码 query 为向量 |
| `vector_service/chroma_store.py` | 146-190 | `ChromaStore.query()` — Chroma Top-K 查询 |
| `vector_service/config.py` | 1-18 | 常量 (`vector_db/`, `okf_chunks`, `cosine`, `top_k=5`) |
| `tests/test_mcp_tools.py` | (新增两个 test) | `search_chroma` 端到端验证 |

### 使用前提

1. Chroma 中必须有数据：先执行 `python embedding_service/main_import.py --vector-db`。
2. MCP 服务器必须在运行：`python -m doc_service.mcp_main`。
3. Kiro 如需发现新工具，需 reconnect MCP server（命令面板 → "MCP: Reconnect"）。

---

## 当前实现与后续扩展

- **当前检索后端**：MCP 提供三种检索工具——
  - `search_chroma`：**Chroma 向量库** 检索（SBERT → Chroma persistent store）；
  - `search_knowledge`：**SBERT embedding 内存检索**（从 `embedding/*.json` 读入计算）；
  - `query_documents`：**关键词检索**（keyword matching）。
  三者共用同一 MCP 服务器（`:8001/mcp`），但各自使用不同后端。
- **Chroma 状态**：已完成两阶段——Phase 1（CLI 写入 + 查询）和 Phase 2（MCP 接入）。
  `search_chroma` 可直接在 Kiro 中调用。
- **预留扩展点**：`ChromaStore` 独立解耦，未来可继续被实现 `Retriever` 协议的
  `ChromaRetriever` 复用（让 `search_knowledge` 也切换到 Chroma 后端），调用方式不变。
- 后续可考虑（均非当前范围）：更完善的检索抽象、BM25、混合检索、
  重排（reranker）、检索评估、LLM Judge。

## 相关目录

| 路径 | 说明 |
|---|---|
| `doc_service/mcp/server.py` | MCP 服务器与工具定义（`search_chroma`、`search_knowledge`、`query_documents` 等） |
| `doc_service/api/dependencies.py` | 依赖注入：`get_chroma_store()`、`get_local_embedder()`、`get_*_service()` |
| `doc_service/retrieval/` | 检索抽象（`Retriever` 协议）与实现（关键词 / embedding） |
| `doc_service/services/knowledge_service.py` | 服务层统一检索入口 |
| `embedding_service/` | SBERT 编码、相似度检索、embedding 持久化（`main_import.py` 含 `--vector-db` 开关） |
| `embedding/` | 已持久化的 chunk 向量（JSON） |
| `vector_service/` | Chroma 向量库封装（`chroma_store.py`）与 CLI（`cli.py`，`search` / `stats`） |
| `vector_db/` | Chroma 持久化存储目录（gitignore，不入库） |
| `.kiro/skills/enterprise-knowledge.md` | 约束“必须通过 MCP 查询”的技能 |
| `.kiro/settings/mcp.json` | Kiro 侧的 MCP 服务器连接配置 |



# ChromaDB 与向量索引：讨论总结

## 1. Embedding 在 ChromaDB 中是什么

Embedding 可以理解为把一段文本转换成一个高维向量。

例如使用一个 384 维的 embedding model：

V1 = [0.12, -0.03, 0.88, ..., 0.21]
V2 = [0.15, -0.01, 0.82, ..., 0.18]

其中：

- V1 是第 1 条文本对应的完整 384 维向量
- V2 是第 2 条文本对应的完整 384 维向量
- V3、V4……同理
- V1、V2 不是“第 1、2 个维度”，而是“第 1、2 条记录对应的完整 embedding”

一个 Chroma collection 在逻辑上可以理解成：

ID | Embedding | Document | Metadata
---|---|---|---
001 | [384 个浮点数] | Evidence bundle... | document_id, title...
002 | [384 个浮点数] | Authentication... | document_id, title...
003 | [384 个浮点数] | Retention... | document_id, title...

实际磁盘上的 Chroma 数据并不是简单的这种表格，而是由 Chroma 的持久化存储和向量索引共同管理。

---

## 2. 查询时发生什么

用户输入：

"What must an evidence bundle contain?"

首先需要通过 embedding model 把 query 转换成向量：

Query Text
↓
Embedding Model
↓
Query Vector
[384 个浮点数]
↓
Vector Search
↓
Top-K
↓
返回对应的 Document + Metadata

因此，Vector DB 真正比较的是：

Query Vector

与：

Document Vector 1
Document Vector 2
Document Vector 3
...

之间的距离或相似度。

Chroma 本身并不理解“compliance evidence bundle”是什么意思。

它主要负责在向量空间中寻找与 query vector 接近的向量。

---

## 3. 为什么不能逐个比较所有向量

如果数据库中有 100 万条 embedding，最简单的方法是：

Query
↓
计算 Query 与 Vector 1 的距离
↓
计算 Query 与 Vector 2 的距离
↓
...
↓
计算 Query 与 Vector 1,000,000 的距离
↓
排序
↓
Top-K

这种方法属于 brute-force search，数据量大时成本很高。

Vector DB 的核心价值之一，就是通过专门的向量索引减少需要实际计算距离的候选数量。

逻辑上：

Query Vector
↓
Vector Index
↓
快速缩小候选范围
↓
只计算一小部分候选向量
↓
Top-K

---

## 4. HNSW

Chroma 常见的向量索引思路是 HNSW：

Hierarchical Navigable Small World

它属于 ANN：

Approximate Nearest Neighbor

即：

> 近似最近邻搜索。

HNSW 的核心不是把向量本身改变，而是根据向量之间的空间关系建立一个 graph。

例如：

V1 ─── V2
│      │
V3 ─── V4
       │
       V5

这些连接表示某些向量在 embedding space 中比较接近。

因此，HNSW 可以被理解成：

> 一个用于在向量空间中导航的近邻图。

---

## 5. HNSW 为什么是 Hierarchical

HNSW 不是单层 graph，而是多层结构。

概念上：

Layer 2：

A ───────── F

Layer 1：

A ─ B ─── D ─ F ─ G

Layer 0：

更多、更密集的节点和连接

查询时：

Query
↓
从 entry point 开始
↓
在高层快速定位大概区域
↓
下降到下一层
↓
继续寻找更接近的节点
↓
进入底层进行更精细的搜索
↓
Top-K

因此可以把它粗略理解成：

> 高层负责快速跳跃，低层负责精细搜索。

---

## 6. “如果 F 比 A 更接近 X，是不是必须比较 X 和 A、F？”

是。

这个理解是正确的。

如果算法说：

"F 比 A 更接近 X"

那么至少需要计算：

distance(X, A)
distance(X, F)

才能知道 F 更近。

HNSW 并没有让“距离计算”消失。

它解决的问题是：

> 不需要让 X 和所有 100 万个向量比较。

例如 A 有几个邻居：

A → B
A → F
A → K
A → M

那么可以先比较：

distance(X, A)
distance(X, B)
distance(X, F)
distance(X, K)
distance(X, M)

如果 F 更接近，就移动到 F，然后继续探索 F 的邻居。

因此：

Brute Force：

X
├── A
├── B
├── C
├── ...
└── 1,000,000

HNSW：

X
↓
Entry Point
↓
少量邻居
↓
更接近的节点
↓
继续导航
↓
候选集合
↓
Top-K

核心思想不是“避免比较”，而是：

> 把需要比较的候选数量从 N 个缩小到一个很小的集合。

---

## 7. HNSW 不是简单的一条路径

二叉树搜索可以粗略理解成：

A
↓
B
↓
C
↓
D

每次选择一个分支。

HNSW 是 graph，不是 tree。

一个节点可能有多个邻居：

A ─── B
│   ╱ │
C ─── D
│     │
E ─── F

搜索过程中可以维护多个 candidate，而不是永远只沿着一条路径走。

这也是 HNSW 能够降低搜索错误、提高 recall 的重要原因之一。

---

## 8. 插入新向量时发生什么

假设已经有一个 HNSW graph，现在插入新的向量 X。

不是：

X
↓
与所有现有向量计算距离
↓
找到真正最近的 N 个
↓
插入

而是：

新 Vector X
↓
利用已有 HNSW graph 导航
↓
寻找 candidate neighbors
↓
选择合适的邻居
↓
建立 graph connections
↓
把 X 加入 HNSW

因此，HNSW 的 index 是随着数据插入逐渐建立和更新的。

建索引时也不是要求找到数学意义上的“全库绝对最近邻”。

---

## 9. efConstruction

HNSW 建索引时有一个重要参数：

efConstruction

可以粗略理解为：

> 建立 graph 时，愿意花多少计算量寻找新节点的候选邻居。

通常可以理解为：

efConstruction 越大
↓
建索引成本越高
↓
graph 质量通常更好
↓
查询 recall 通常更高

因此这里存在：

速度 / 建索引成本 / recall

之间的 trade-off。

---

## 10. HNSW 与二叉树 / B-tree 的类比

把 HNSW 类比成二叉树或者 B-tree，作为第一阶段的 mental model 是有帮助的：

二叉树 / B-tree：

> 利用已有的层级结构缩小搜索范围。

HNSW：

> 利用已有的多层近邻 graph 缩小搜索范围。

但是不能直接认为：

HNSW = Tree

也不能简单认为：

HNSW 查询或插入 = O(H)

因为 HNSW 是 graph，而且搜索过程中还受到很多因素影响，例如：

- M
- efSearch
- efConstruction
- layer 数量
- graph 的实际结构

所以更准确的理解是：

Brute Force：

O(N) 级别的全量搜索

Tree：

利用层级结构降低搜索空间

HNSW：

利用多层近邻 graph 快速导航，只探索一小部分候选节点

---

## 11. 最重要的 Mental Model

可以把整个过程浓缩成：

文本
↓
Embedding Model
↓
384 维向量
↓
V1 / V2 / V3 / ...
↓
根据向量距离建立近邻关系
↓
HNSW Graph
↓
Query Text
↓
Query Embedding
↓
HNSW Navigation
↓
Candidate Vectors
↓
Top-K
↓
Document + Metadata

最关键的一句话：

> Embedding 把语义转换成向量空间中的位置；HNSW 利用这些位置之间的近邻关系建立导航图，从而避免每次查询都扫描所有向量。