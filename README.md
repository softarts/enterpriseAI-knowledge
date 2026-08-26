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
> 因此未来可被一个查询 Chroma 的 MCP 工具直接复用，无需改动。**本阶段不修改现有 MCP。**

---

## 当前实现与后续扩展

- **当前检索后端**：MCP 的 `search_knowledge` 走 **SBERT embedding 向量检索**
  （从 `embedding/*.json` 读入内存计算）；`query_documents` 走**关键词检索**，
  二者共用同一个 `Retriever` 协议。
- **Chroma（第一阶段）**：已通过 `--vector-db` 把向量写入 `vector_db/`，并提供
  `vector_service` CLI 做 `stats` / `search`，独立验证 Embedding → Chroma →
  Vector Search。**现有 MCP 尚未接 Chroma**（本阶段不改 MCP）。
- **预留扩展点**：`ChromaStore` 已与其它模块解耦，未来可由查询 Chroma 的 MCP 工具或
  一个实现 `Retriever` 协议的 `ChromaRetriever` 直接复用，调用方式保持不变。
- 后续可考虑（均非当前范围）：让 MCP 查询 Chroma、更完善的检索抽象、BM25、混合检索、
  重排（reranker）、检索评估、LLM Judge。

## 相关目录

| 路径 | 说明 |
|---|---|
| `doc_service/mcp/server.py` | MCP 服务器与工具定义（`search_knowledge` 等） |
| `doc_service/retrieval/` | 检索抽象（`Retriever` 协议）与实现（关键词 / embedding） |
| `doc_service/services/knowledge_service.py` | 服务层统一检索入口 |
| `embedding_service/` | SBERT 编码、相似度检索、embedding 持久化（`main_import.py` 含 `--vector-db` 开关） |
| `embedding/` | 已持久化的 chunk 向量（JSON） |
| `vector_service/` | Chroma 向量库封装（`chroma_store.py`）与 CLI（`cli.py`，`search` / `stats`） |
| `vector_db/` | Chroma 持久化存储目录（gitignore，不入库） |
| `.kiro/skills/enterprise-knowledge.md` | 约束“必须通过 MCP 查询”的技能 |
| `.kiro/settings/mcp.json` | Kiro 侧的 MCP 服务器连接配置 |


==
Chroma 第一阶段集成已完成并实测通过。

完成内容
新增 vector_service/ 包

chroma_store.py — ChromaStore：add_embedded_chunks(以 chunk_id 幂等 upsert)、query(Top-K 最近邻)、stats。不自己编码文本(调用方传向量),便于将来 MCP 复用。
cli.py — python -m vector_service.cli search "..." [--top-k N] 和 stats。
config.py — vector_db/、collection okf_chunks、cosine、默认 Top-K=5。
修改 
main_import.py

新增 --vector-db(默认关)与 --vector-db-dir。默认行为完全不变:仍写 embedding/*.json,且只有加开关时才 import chromadb、写 vector_db/。
其它

requirements.txt 加 chromadb>=1.5.0(实际安装 1.5.9);.gitignore 加 vector_db/。

agents.md
 固化“每个完成的 task 必须写 task summary”规则。

2026-08-26-chroma-vector-db-phase1.md
 记录实现/测试/限制。
README.md 新增“Chroma / Vector DB”章节:写入与查询示例、对应代码文件+行号、以及与现有风格一致的流程图。
实测结果
导入:python embedding_service/main_import.py --vector-db → 8 文件成功,collection okf_chunks 写入 43 条。
stats → count=43, cosine, dim=384。
search "...compliance evidence bundle?" --top-k 3 → Top-1 distance 0.4110(chunk-014,"Acceptance criteria for compliance reviewers"),与之前内存检索的相似度 0.589 吻合(distance ≈ 1 − score),顺序一致。
约束遵守
本阶段只验证 Embedding → Chroma → Vector Search;未引入 BM25/reranker/hybrid/LLM/context assembly,未改动现有 MCP。ChromaStore 已解耦,为未来“MCP 查询 Chroma”预留了复用点。

一点说明:heading 为空时因 Chroma 元数据不接受 None,写入时转为 ""、读出时再转回 None;删除 generated/ 中的 chunk 不会自动从 Chroma 移除(第一阶段无对账/删除逻辑),这些都记在了 task summary 的“已知限制”里。