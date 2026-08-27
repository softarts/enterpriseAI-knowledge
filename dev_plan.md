
### 完成度打分

| 模块 | 完成度 | 说明 |
|------|--------|------|
| 文档导入 (Raw→OKF) | 90% | 能跑通，但缺少增量/清理逻辑 |
| Chunking | 60% | heading-aware Markdown 切块可用，但策略单一 |
| Embedding 生成 | 95% | LocalEmbedder 完整，--vector-db 双写 |
| 向量存储 (JSON) | 100% | 稳定运行 |
| 向量存储 (Chroma) | 85% | 写入/查询/stats 可用，缺 reconciliation |
| 检索 (keyword) | 80% | 可用，CJK 支持，但无 BM25 |
| 检索 (embedding) | 85% | 两条路径可用 (in-mem + Chroma) |
| MCP 接口 | 95% | 5 个工具稳定，Kiro 可直接调用 |
| REST API | 90% | 完整 CRUD + search |
| 检索评估 | 75% | 20 queries, Hit/MRR, 缺 LLM judge |
| LLM 生成 / RAG | 0% | **完全没有** |
| Agent Harness | 0% | **完全没有** |
| CI/CD | 0% | 没有自动化 |

### 关键差距

1. **没有 LLM 生成层**：当前系统是 "retrieval-only backend"，回答能力完全依赖外部 Kiro。
2. **没有 Agent 循环**：无 ReAct、无 tool-use orchestration、无状态/记忆管理。
3. **检索质量优化空间大**：单一 embedding 模型 + 无 BM25 + 无 reranker。
4. **缺失 requirements.txt 依赖**：sentence-transformers、pytest-asyncio 未列出。
5. **无 ChromaRetriever Protocol 实现**：search_chroma 绕开了 Retriever 协议。

---

## 二、工程角度 — RAG 技术点实现路线

### Phase 1: 基础 RAG 闭环 (已完成)

- [x] Raw 文档 → OKF 标准化
- [x] OKF → heading-aware chunking
- [x] Chunk → SBERT embedding
- [x] Embedding → JSON / Chroma 持久化
- [x] 查询 → embedding → 向量检索 → Top-K
- [x] MCP 接口 → Kiro 可调用
- [x] 检索评估 (Hit@K, MRR)

### Phase 2: 端到端 RAG (接下来要做)

- [ ] LLM Client (OpenAI-compatible, env-driven)
- [ ] Prompt Template (system + context + query)
- [ ] Context Assembly (Top-K chunks → structured prompt)
- [ ] Answer Generation (LLM 合成 grounded answer)
- [ ] Citation Extraction (生成引用来源)
- [ ] RAG Evaluation: LLM-as-Judge (correctness, faithfulness, citation, completeness)
- [ ] Failure Classification (retrieval_failure / generation_failure / citation_failure)

### Phase 3: 检索质量提升

- [ ] BM25 Retriever
- [ ] Hybrid Search (BM25 + vector, RRF 融合)
- [ ] Cross-encoder Reranker
- [ ] ChromaRetriever (统一到 Retriever 协议)
- [ ] Metadata filtering (by source, tag, date)

### Phase 4: 工程健壮性

- [ ] requirements.txt 补全 (sentence-transformers, pytest-asyncio)
- [ ] CI pipeline (GitHub Actions: lint + test + evaluation regression)
- [ ] Chroma reconciliation (删除/更新 chunk 时同步 Chroma)
- [ ] Embedding model versioning (换模型时自动 re-embed)
- [ ] Streaming response 支持

---

## 三、Agent Harness 角度 — 有了 LLM API Key 后能做什么

> 以下每个主题在 AI Engineer 面试中都是高频考察点。

### 3.1 Agentic Engineering Workflows (工具编排)

当前 MCP 只是暴露工具给外部 Kiro 调用。如果你自己持有 LLM API Key，可以构建：

**Plan-and-Execute Agent**
