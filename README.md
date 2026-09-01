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

---

## Chat Playground（chat_service + 前端）

`chat_service/` 是一个独立的对话后端 + React 前端 playground，目前实现的是直连
Hugging Face LLM 的单轮 Ask 流程：`question → HF LLM → answer + trace`。

### 1. 对话历史记录：存在哪、怎么渲染

**历史记录保存在前端（浏览器内存），不在后端。**

后端 `chat_service` 是**无状态的**：`POST /api/chat` 每次只接收单个 `question`
（见 `chat_service/models.py` 的 `ChatRequest`，只有一个 `question` 字段），
返回单条 `answer + trace`，服务端不保存任何历史。`ChatService` 也标注了
`stateless; safe to reuse`（`chat_service/api/routes_chat.py:19`）。

历史记录完全由前端 React 的组件 state 持有：

| 关注点 | 位置（文件:行号） | 说明 |
|---|---|---|
| 历史记录状态 | `chat_service/frontend/src/App.jsx:11` | `const [messages, setMessages] = useState([])` —— 整个对话数组 |
| 追加用户消息 | `chat_service/frontend/src/App.jsx:18` | 发送时把 `{role:"user", content}` push 进 messages |
| 追加助手/错误消息 | `chat_service/frontend/src/App.jsx:27-40` | 收到响应后追加 `{role:"assistant"...}` 或 `{role:"error"...}` |
| 渲染消息列表 | `chat_service/frontend/src/components/ChatWindow.jsx:38-40` | `messages.map(...)` 逐条渲染 |
| 单条气泡渲染 | `chat_service/frontend/src/components/Message.jsx` | 按 `role`（user / assistant / error）渲染不同样式的气泡 |
| 自动滚动到底部 | `chat_service/frontend/src/components/ChatWindow.jsx:11-13` | `useEffect` + `scrollIntoView` |
| 调用后端 | `chat_service/frontend/src/api/chatApi.js:17` | `fetch("/api/chat", ...)` |

渲染流程：

```
用户输入
  → App.handleSend()  (App.jsx:17)
     → setMessages 追加 user 消息      (App.jsx:18)
     → askQuestion() 调用后端           (chatApi.js:17)
     → setMessages 追加 assistant 消息  (App.jsx:31)
  → <ChatWindow messages> 重新渲染       (ChatWindow.jsx)
     → messages.map → <Message>          (ChatWindow.jsx:38)
```

**重要含义**：因为历史只在前端内存里，**刷新页面就会清空对话**；而且由于后端每次
只收到当前 `question`（不带历史），LLM **没有多轮上下文记忆**。若要做多轮记忆，需要
前端把历史一起发给后端，或在后端引入 session/持久化（当前未实现）。

### 2. 为什么限制 `max_tokens`，会不会截断 LLM 响应

你看到的这段是后端 trace 里记录的 LLM 调用元数据：

```json
{
  "provider": "huggingface",
  "model": "openai/gpt-oss-120b",
  "max_tokens": 512,
  "finish_reason": "length",
  "usage": { "prompt_tokens": 97, "completion_tokens": 512, "total_tokens": 609 }
}
```

`max_tokens` 在 `chat_service/llm/hf_client.py` 里作为
`client.chat.completions.create(..., max_tokens=self.max_tokens)` 传给 HF API，
默认值来自配置（512）。

**为什么要限制**：
- **控制成本与延迟**：completion tokens 越多，费用和响应时间越高。
- **防止失控输出**：给模型输出设一个安全上限。
- 注意 `max_tokens` **只限制“生成部分（completion）”的长度，不影响 prompt**。上例
  `prompt_tokens=97` 不受影响，被限制的是 `completion_tokens`。

**是否会截断**：**会**。关键信号是 `finish_reason: "length"` 且
`completion_tokens == max_tokens (512)`——这说明模型是因为**触达 token 上限被强制停止**，
而不是自然把话说完（自然结束时 `finish_reason` 通常是 `"stop"`）。所以这次响应
**确实被截断了**。

**怎么办**：
- 需要更长答案时，调高 `max_tokens`（见下一节，改配置或设 `CHAT_MAX_TOKENS`）。
- 在 UI/trace 中把 `finish_reason == "length"` 显式提示为“答案可能被截断”。
- （后续）支持续写：把已生成内容作为上下文再请求一次继续生成。

### 3. 把 model / api_key 放进配置文件（api_key 指向环境变量）

已实现：新增 `chat_service/llm_config.yaml`，把非机密的 LLM 设置和 token 的**引用**
集中管理。**`api_key` 存的是环境变量引用 `${HF_TOKEN}`，不是真实 token**：

```yaml
# chat_service/llm_config.yaml
provider: huggingface
model: openai/gpt-oss-120b
api_key: ${HF_TOKEN}   # 指向环境变量，不是真实密钥
max_tokens: 512
```

加载逻辑在 `chat_service/config.py`：

| 功能 | 位置 | 说明 |
|---|---|---|
| `${VAR}` 解析 | `chat_service/config.py:_resolve_env_refs` | 把字符串里的 `${VAR}` 替换成对应环境变量值 |
| 读取 YAML | `chat_service/config.py:_load_llm_config` | 读 `llm_config.yaml` 并解析引用 |
| 记住 token 变量名 | `chat_service/config.py:_extract_token_env_var` | 从 `api_key: ${HF_TOKEN}` 里解析出变量名 `HF_TOKEN` |
| 实际取 token | `chat_service/config.py` 的 `hf_token()` | 运行时从该环境变量读取，token 值**从不**存到对象上 |

**解析优先级**：环境变量（`CHAT_MODEL` / `CHAT_MAX_TOKENS`）> `llm_config.yaml` > 内置默认值。

**安全要点**：
- 真实 token 只存在于环境变量 `HF_TOKEN`，配置文件里只有引用 `${HF_TOKEN}`，可安全提交。
- token 值不会被 log、不返回前端、也不存在 `settings` 对象上（`/api/health` 只返回
  `hf_token_configured: true/false`，见 `routes_chat.py`）。
- 想换 token 来源变量名，只需改 YAML 里的 `api_key: ${OTHER_VAR}`，代码会自动跟随。

用法：

```bash
# 1) 在环境变量里放真实 token（不要写进任何文件）
set HF_TOKEN=hf_xxx            # Windows (cmd)
$env:HF_TOKEN="hf_xxx"        # Windows (PowerShell)
export HF_TOKEN=hf_xxx         # macOS / Linux

# 2) 模型 / max_tokens 改配置文件 chat_service/llm_config.yaml 即可
#    （或用 CHAT_MODEL / CHAT_MAX_TOKENS 环境变量临时覆盖）

# 3) 启动
python -m chat_service.run
```

---

## Taxonomy Classifier（逐篇分类器 / kb_classifier 阶段 B）

`kb_classifier/taxonomy_classifier/`（原 `stage_b`）是 KB 分类流水线的**稳态、
生产 API**：给一篇（或一批）文档打上三级 taxonomy 路径。它在**文档导入时**被调用，
只读消费阶段 A 冻结产物（taxonomy + thresholds），**不聚类、不调用 LLM**，每篇只做
几次点积，因此足够便宜可内联到导入流程里。

### 流程说明

```
一篇文档 (title, body)
  ↓  BGE-M3 编码（与阶段 A 相同的 embed 渲染：title 加权 + 截断）
文档向量 (L2 归一化)
  ↓  match_hierarchical：全局叶子路径最优匹配（L3 最优并回溯 L2/L1）
每级 (key, score)
  ↓  读 thresholds.json，逐级阈值判定：
      L1 分数 < 阈值        → 触发 Deep Fallback（若 L2/L3 过阈值则为 FALLBACK，否则 UNKNOWN）
      L1 过、L2 分数 < 阈值 → PARTIAL（截到 L1）
      L1L2 过、L3 < 阈值    → PARTIAL（截到 L2）
      三级都过             → ASSIGNED（完整 L1>L2>L3）
  ↓
OKF 分类 metadata（路径 keys/names + 每级分数 + status），供下游 RAG 做
metadata 过滤 + 混合检索
```

**冻结版本**：分类器默认锁定生产 taxonomy 版本
`PINNED_TAXONOMY_VERSION = 7`（→ `config/taxonomy_v7.py`），
不会随阶段 A 每轮生成而漂移。要升级生产版本，只改这一个常量；用
`--taxonomy-version` 可临时覆盖。

### 涉及的代码（文件:行号）

| 步骤 | 符号 | 文件:行号 |
|---|---|---|
| 冻结的生产版本号 | `PINNED_TAXONOMY_VERSION = 7` | `kb_classifier/taxonomy_classifier/classify.py:73` |
| 分类器（构造即就绪，可复用） | `class TaxonomyClassifier` | `kb_classifier/taxonomy_classifier/classify.py:137` |
| 加载 taxonomy + 阈值 + anchor 向量 | `TaxonomyClassifier.__init__` | `kb_classifier/taxonomy_classifier/classify.py:148` |
| 逐级阈值判定 → status | `_apply_thresholds` | `kb_classifier/taxonomy_classifier/classify.py:203` |
| 向量批分类（match_hierarchical） | `classify_vectors` | `kb_classifier/taxonomy_classifier/classify.py:300` |
| 文档批分类（先编码后分类） | `classify_documents` | `kb_classifier/taxonomy_classifier/classify.py:328` |
| 单篇 (title, body) 分类 | `classify_text` | `kb_classifier/taxonomy_classifier/classify.py:340` |
| 生成 OKF metadata | `Classification.to_okf_metadata` | `kb_classifier/taxonomy_classifier/classify.py:113` |
| 回归测试套件 | `test_classifier_regression` | `kb_classifier/test_classifier_regression.py` |
| 冻结版本解析（pin/latest/seed） | `load_current_taxonomy` | `kb_classifier/config/taxonomy_current.py:88` |
| 全局叶子最优路径匹配 | `match_hierarchical` | `kb_classifier/common/matching.py:66` |
| taxonomy 展平为 anchors | `flatten_taxonomy` / `embed_anchors` | `kb_classifier/common/anchors.py` |
| 向后兼容别名 | `Classifier = TaxonomyClassifier` | `kb_classifier/taxonomy_classifier/classify.py:353` |

### 实验：分类一个文件

先决条件：阶段 A 产物已存在（`config/taxonomy_v6_50k.py`、`config/thresholds.json`、
anchor 向量缓存）。首次运行会下载 BGE-M3 模型（约 2GB，一次性；设置 `HF_TOKEN`
可加速）。

```bash
# 单篇：从 .txt 文件（首个非空行=title，其余=body）
python -m kb_classifier.taxonomy_classifier.classify file "all_documents\confluence\company-handbook\dsid_9922ca0efee74e4fabcd4c4bab756ad6__career-neighborhoods-and-benefits-playbook-2027.txt"

# 单篇：直接给 title/body
python -m kb_classifier.taxonomy_classifier.classify text --title "Compliance evidence bundle" --body "The manifest must contain evidence_id, time_window, signing_key_id, signature ..."

# 临时用别的 taxonomy 版本
python -m kb_classifier.taxonomy_classifier.classify file <path> --taxonomy-version 5
```

初始化日志（已验证）：

```
[taxonomy] pinned taxonomy = taxonomy_v6_50k.py
[anchors] loaded 351 cached anchor vectors from kb_classifier/work/anchor_embeddings.npz
[taxonomy_classifier] ready: taxonomy=taxonomy_v6_50k.py (351 anchors),
                      thresholds L1=0.4731 L2=0.4412 L3=0.4507
[embed] loading BAAI/bge-m3 on cpu ...
```

输出为一条 OKF 分类 metadata（`to_okf_metadata` 的结构）：

```json
{
  "classification_status": "ASSIGNED",
  "classification_depth": 3,
  "category_path_keys": ["<l1_key>", "<l2_key>", "<l3_key>"],
  "category_path_names": ["<L1 名称>", "<L2 名称>", "<L3 名称>"],
  "category_breadcrumb": "<L1> > <L2> > <L3>",
  "level_scores": { "L1": 0.6xx, "L2": 0.5xx, "L3": 0.5xx },
  "l1_key": "<l1_key>", "l2_key": "<l2_key>", "l3_key": "<l3_key>"
}
```

`status` 三种取值：`ASSIGNED`（三级齐全）、`PARTIAL`（截断在 L1 或 L2）、
`UNKNOWN`（连 L1 阈值都没过）。

### 批量入库（doc_id → 分类路径 映射）

```bash
# 对 manifest 里所有文档逐篇打标，落一份 jsonl（每行一篇）
python -m kb_classifier.taxonomy_classifier.classify batch --out work/taxonomy_labels.jsonl

# 先小批量试跑
python -m kb_classifier.taxonomy_classifier.classify batch --limit 200 --out work/taxonomy_labels.jsonl
```

`classify_corpus` 会复用冻结的 `work/manifest.jsonl`（doc_id 与阶段 A / OKF 流水线
对齐），分批读取+编码，每行写 `doc_id + 分类 metadata + rel_path/source/title`，
最后打印 ASSIGNED / PARTIAL / UNKNOWN 占比。

### 作为库在导入流程中调用

```python
from kb_classifier.taxonomy_classifier import TaxonomyClassifier

clf = TaxonomyClassifier()                       # 构造一次（加载冻结 taxonomy + 351 anchors）
result = clf.classify_text(title, body)          # 单篇
metadata = result.to_okf_metadata(doc_id=doc_id) # → 写入文档 metadata
# 批量：clf.classify_documents(docs)
```

> 复用要点：`TaxonomyClassifier` 构造一次即可反复调用，**不要每篇都重建**
> （重建会重新加载模型和 anchors）。单文档导入用 `classify_text`，多文档用
> `classify_documents(docs)`。

### 分类不准确问题分析与修复（v6 → v7 + margin gate）

在用两份真实文档验证时，v6 taxonomy 出现了**自信但错误**的分类。这里记录根因分析
和已做的修复，作为后续调优的参考。

#### 两个失败案例

| 文档 | 真实类别 | v6 分类结果（错误） |
|---|---|---|
| Career Neighborhoods and Benefits Playbook（HR/人才/福利） | `human_resources` | `Technology & Engineering > AI & ML Platform > Prompt & Retrieval Engineering` |
| Alert-fatigue telemetry dedup retrospective（SRE/可观测性） | `technology_engineering > site_reliability_observability` | `Billing Anomalies > Duplicate Webhook Events > Hosted API Outages` |

两份文档的各级得分都只有 ~0.50，勉强越过阈值（L1=0.4731），却给了自信的
`ASSIGNED`。

#### 根因（用逐级得分排名确认，非猜测）

分类是**一次性把文档向量和全部 anchor 做余弦相似度取 argmax 的分层匹配**，没有
"先判断公司/领域再进对应分支"的逻辑。因此有两个独立的失败机制：

1. **发现的"垃圾" L1 节点劫持顶层决策（SRE 案例）**
   Stage A 的 HDBSCAN 从科技语料里碎片化出的窄主题（`billing_anomalies`、
   `performance_monitoring`、`sdk_onboarding_issues`、`model_serving_monitoring`、
   `release_operations`、`redwood_demo_coordination`）被**错误地放成了 L1**，
   和 `technology_engineering` 平级。对 SRE 文档，这些垃圾节点排在 L1 前 4，正确的
   `technology_engineering` 只排第 6。而分层匹配**先定 L1、再只看其子节点**，所以
   一旦垃圾 L1 险胜，正确分支下那个**全树最高分**的节点
   （`site_reliability_observability`，0.5663）就被彻底锁在了外面。

2. **弱信号下的近似平局（HR 案例）**
   即使移除垃圾节点，HR 文档在 L1 上 `technology_engineering`(0.5137) 仅以 **0.0065**
   险胜正确的 `human_resources`(0.5072)。原因是这份 HR playbook 本身塞满了工程词汇
   （GPU/infra/Okta/GCP neighborhoods、CLI 片段），whole-document 单向量把主题信号
   稀释了，argmax 近乎随机。

3. **底层根因：taxonomy 与语料领域不匹配**
   v6 约 90% 是**银行业务** taxonomy（Retail Banking / Payments / Lending / Treasury…），
   但真实语料是**科技/AI 公司**（LLM 推理、GPU、SRE、prompt engineering）。多数文档
   没有理想归属，容易被最近的银行/垃圾 anchor 以微弱优势抢走。

> 关键结论：**"有银行分支"不是 bug，"正确分支只能得 ~0.50 分、且区分度极小"才是 bug。**
> 阈值 0.47/0.44/0.45 太低，无法拦截错误匹配。

#### 已做的修复

1. **`taxonomy_v7.py`（纯字典编辑，不重扫 50k 语料）**
   从 v6 删除 6 个错放的"发现型垃圾 L1 节点"，剩 17 个全为 seed 节点。这直接修复
   SRE 案例（`technology_engineering` 得以上位，其强子节点胜出）。
   - 产出方式：只编辑 taxonomy 字典 → anchor 向量按内容指纹**自动重建**（~350 段
     描述，约 1 分钟），**不需要重跑 Stage A / 重扫 50k 文档**。
   - 生产版本冻结：`PINNED_TAXONOMY_VERSION = 7`
     （`kb_classifier/taxonomy_classifier/classify.py`）。

2. **L1 margin gate（新增 `AMBIGUOUS` 状态）**
   `L1_MIN_MARGIN = 0.02`：当 L1 top1 − top2 的分差小于该值时，判为 `AMBIGUOUS`
   而不是给一个自信的错误路径。修复 HR 这类近似平局案例（0.0065 < 0.02 → AMBIGUOUS）。
   实现只多做一次对 ~17 个 L1 anchor 的点积，成本可忽略。
   - 位置：`_apply_thresholds` / `_l1_margins`
     （`kb_classifier/taxonomy_classifier/classify.py`）。

3. **anchor cache 写入健壮性（Windows WinError 5 修复）**
   `embed_anchors` 原来用 `os.replace` 原子替换 `anchor_embeddings.npz`，在 Windows 上
   被杀毒/文件索引/云同步临时锁定目标文件时会抛 `PermissionError [WinError 5]`。改为
   "唯一临时文件 + 重试退避 + 回退删后重命名 + 回退直写 + 最终仅告警不崩溃"
   （`kb_classifier/common/anchors.py`）。缓存只是优化，写不成也不影响分类结果。
   - 建议：把 `kb_classifier/work/` 目录加入 Windows Defender 排除项，可彻底消除该锁。

#### 状态语义（含新增）

- `ASSIGNED`：三级齐全且各级过阈值、L1 区分度足够。
- `PARTIAL`：某一级低于阈值，路径截断在上一级。
- `AMBIGUOUS`：**新增** —— L1 近似平局（top1−top2 < margin），不可信。
- `UNKNOWN`：连 L1 阈值都没过。

#### 尚未做 / 后续建议

- **重新拟合 / 提高阈值**：0.47/0.44/0.45 太宽松。
- **分段分类再聚合**：长的混合主题文档（如 HR playbook 混大量工程词）用整篇单向量会
  稀释主题信号；按 section 分类再聚合更稳。
- **更强的标题加权**：标题往往是最强主题信号，可进一步上调权重。
- **是否为科技语料重建 taxonomy**：v6/v7 骨架仍偏银行，可考虑用科技导向的 seed 重跑
  Stage A（这是较大的战略性改动）。
- **批量失败分类**：把 `AMBIGUOUS` 纳入 batch 的失败统计与分析。

> 现状建议：在完成上述阈值/分段改进并在一批带标注文档上量化准确率之前，
> **不要对全量语料做批量打标**。两份手挑文档都曾自信地分错，说明当前配置尚未达到
> 生产可信度。

---

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

---

# chat_service — Enterprise AI Playground（对话 + 文档导入）

`chat_service` 是一个**独立**的服务模块，实现了一个最小可用的 Enterprise AI
Playground Web UI，并把前后端跑通。它与 `doc_service` / `vector_service` / MCP
解耦：当前支持 Ask 对话和单文件 Documents 导入。Ask 流程调用 Hugging Face Cloud LLM，
导入流程负责原始文件保存、文本提取和 taxonomy 自动分类。**当前不接 Chroma、不接 MCP、不做 RAG。**

## 流程图

```
Browser (React UI, :5173)
   |
   |  POST /api/chat  { question }
   v
chat_service (FastAPI, :8100)
   |  ChatService.ask()  ->  [request step]
   |                          (RAG seam: 未来在此插入 vector_service.search())
   v
Hugging Face Cloud LLM  (openai/gpt-oss-120b, InferenceClient)
   |
   v
Answer + Trace  ->  { answer, trace{ steps[], request, llm, response }, error }
   |
   v
Browser: 中间显示回答，右侧 Trace 面板显示真实执行过程
```

### 文档导入流程（当前实现）

```
Browser Documents
  -> POST /api/documents/import (multipart file)
  -> ImportService.import_file()
       校验 -> 原始 bytes 写入 temp -> 提取 title/body
       -> TaxonomyClassifier.classify_text(title, body)
       -> SQLite 写入 pending 元数据 -> 返回分类
  -> POST /api/documents/import/{id}/confirm
  -> ImportStorage.finalize(): temp -> permanent
  -> SQLite import_state=imported
```

上传接口完成解析和分类后文件仍在 `chat_service/import_data/temp/`，数据库状态为
`pending` 且 `storage_path` 为 `null`；确认后原始文件才移动到永久目录：

```
chat_service/import_data/storage/documents/{shard}/{uuid}_{safe_original_filename}
```

其中 `{shard}` 为 `int(md5(uuid), 16) % 256` 的三位目录（`000` 到 `255`）。文件按 UUID
分片，分类不会决定文件目录，重新分类不会移动文件。

## 前后端结构

```
chat_service/
  config.py                 # 从环境变量读取 HF_TOKEN / 模型 / 端口 / CORS（token 不入代码）
  models.py                 # ChatRequest{question} / ChatResponse{answer, trace, error}
  trace.py                  # TraceBuilder：可扩展 trace（steps[] + request/llm/response）
  llm/hf_client.py          # HuggingFaceLLM：InferenceClient(api_key=HF_TOKEN, provider="auto")
  services/chat_service.py  # ChatService.ask()：编排 request -> LLM -> response；含 RAG 预留接口
  api/routes_chat.py        # GET /api/health, POST /api/chat
  main.py                   # FastAPI app + CORS
  run.py                    # python -m chat_service.run（uvicorn :8100）
  frontend/                 # React + Vite（:5173，/api 代理到 :8100）
    src/App.jsx             # 顶层状态：messages / loading / trace / 折叠开关
    src/components/
      Layout.jsx            # 三段式栅格外壳；中间随两侧折叠自适应
      Sidebar.jsx           # 左侧：可折叠，Chat / Documents / Settings 菜单入口
      ChatWindow.jsx        # 中间：消息列表 + loading + 输入框
      Message.jsx           # 单条消息气泡（user / assistant / error）
      InputBox.jsx          # 输入框（Enter 发送，Shift+Enter 换行）
      TracePanel.jsx        # 右侧：可折叠，渲染后端返回的真实 trace（非 mock）
    src/api/chatApi.js      # askQuestion() -> POST /api/chat
    src/components/ImportPage.jsx # Documents 导入页面
    src/components/UploadArea.jsx # 上传、预览分类、确认导入
```

## UI：三段式布局

- **左侧 Sidebar**：可展开/隐藏，切换 Chat 和 Documents 页面。
- **中间对话区**：显示用户问题与 LLM 回答，底部为输入框；支持 loading、错误、正常回答三种状态。
- **右侧 Verbose / Trace 面板**：可展开/隐藏，显示本次请求的**真实**执行过程
  （每个 step 的 name / status / detail / 耗时）。
- 左右两侧折叠时，中间对话区自动自适应宽度。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/health` | 返回服务状态、模型名、`hf_token_configured`（布尔，不返回 token 本身） |
| `POST` | `/api/chat` | 输入 `{ question }`，返回 `{ answer, trace, error }` |
| `POST` | `/api/documents/import` | 上传单个文件，解析 + 分类，返回 `pending` 记录 |
| `GET` | `/api/documents/import/{id}` | 查询导入记录 |
| `POST` | `/api/documents/import/{id}/confirm` | 将 temp 原始文件移入永久 storage |
| `GET` | `/api/taxonomy` | 返回只读的 v7 taxonomy 树 |

## 导入存储与 classifier 调用

导入默认使用 `chat_service/import_data/`：待确认的原始文件位于
`temp/documents/{shard}/`，确认后移动到 `storage/documents/{shard}/`；元数据和分类结果
写入 `documents.db` 的 `documents_import` 表（字段包括 `category_level_1/2/3`、
`taxonomy_version`、`classification_status` 和 `raw_status`）。永久文件格式为
`documents/{shard}/{uuid}_{safe_original_filename}`。实现见
`chat_service/import_storage.py:4-22, 38-59, 87-111` 和 `chat_service/config.py:104-121`；
可用 `CHAT_IMPORT_DB`、`CHAT_IMPORT_STORAGE_DIR`、`CHAT_IMPORT_TEMP_DIR` 覆盖路径。

上传接口只创建 `pending` 记录；`POST /api/documents/import/{id}/confirm` 才执行
`temp -> permanent` 移动并更新为 `imported`。原始文件保持不变，分类不会影响存储目录。

classifier 的实际调用点是 `chat_service/services/import_service.py:144-148`：

```python
title, body = self._extract_text(temp_path)
classifier = self._get_classifier()
cl = classifier.classify_text(title, body)
```

`import_service.py:74-85` 负责懒加载；`import_service.py:153-169` 将
`cl.to_okf_metadata()` 的三级路径写入 SQLite。内部链路为
`kb_classifier/taxonomy_classifier/classify.py:340-349` → `328-338` → `300-326` →
`common/matching.py:85-123`，再由 `classify.py:203-239` 应用阈值；L1 失败时走
`classify.py:242-298` 的 deep fallback。生产 taxonomy 固定为 v7（`classify.py:73`）。

导入是同步单文件 MVP，支持 `.pdf`、`.docx`、`.doc`、`.html`、`.htm`、`.txt`、`.md`、
`.rst`，默认上限 25 MB；当前没有认证、异步任务、人工重新分类、OKF 转换、切块、搜索
或文件下载 API。完整导入验证见 `chat_service/test_import_e2e.py:15-186`。

`trace` 结构（可扩展）：

```json
{
  "trace_id": "…", "duration_ms": 1835.45,
  "steps": [
    { "name": "request",  "status": "ok", "detail": { … } },
    { "name": "llm",      "status": "ok", "detail": { "provider": "huggingface", "model": "…", "usage": { … } }, "duration_ms": 1835.43 },
    { "name": "response", "status": "ok", "detail": { "answer_chars": 6 } }
  ],
  "request": { … }, "llm": { … }, "response": { … }
}
```

## 当前 Ask 请求流程

1. 前端 `POST /api/chat`，body 为 `{ question }`。
2. `ChatService.ask()` 记录 `request` step。
3. `HuggingFaceLLM.chat()` 用 `InferenceClient(api_key=HF_TOKEN, provider="auto")`
   调用 `chat.completions.create(model="openai/gpt-oss-120b", …)`，记录 `llm` step（含 token usage）。
4. 记录 `response` step，返回 `{ answer, trace }`。
5. 缺少 token 或上游报错时，返回 `error` 字段并把对应 step 标记为 `error`，UI 会渲染错误信息。

## 如何启动

后端（终端 1，需先在环境中设置 `HF_TOKEN`）：

```powershell
$env:HF_TOKEN = "hf_xxx"
python -m chat_service.run          # http://localhost:8100
```

前端（终端 2）：

```powershell
cd chat_service/frontend
npm install                          # 首次
npm run dev                          # http://localhost:5173
```

浏览器打开 `http://localhost:5173` 提问即可。**注意**：前端不直接访问 Hugging Face，
所有能力经 `chat_service` API 提供；`HF_TOKEN` 只存在于后端环境变量中。

## 后续接入 Chroma / RAG 的预留位置

`chat_service/services/chat_service.py` 的 `ask()` 中，在 `request` 与 `llm` 两个
step 之间保留了明确注释的 **RAG seam**。未来接入检索时：

1. 在调用 LLM 之前执行检索（例如通过一个薄封装调用 `vector_service.search(question, top_k)`）。
2. 新增一个 `retrieval`（以及可选的 `context`）trace step —— 右侧面板会自动渲染。
3. 把 assemble 后的 context 前置到 LLM prompt。

`POST /api/chat` 的接口、返回结构与前端**均无需改动**，只是 trace 中多出新的 step。

## 必要文件及其职责

见上方“前后端结构”表；核心职责：`hf_client.py`（唯一的 HF 调用点）、
`chat_service.py`（编排 + trace + RAG 预留）、`TracePanel.jsx`（渲染真实 trace）。

> 完整实现说明、验证结果与未实现功能清单见根目录
> [`TASK_COMPLETION_REPORT_chat_service.md`](TASK_COMPLETION_REPORT_chat_service.md)。
