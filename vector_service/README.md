# Vector Service

`vector_service` provides the ChromaDB persistence adapter for precomputed
embeddings. The BGE-M3 import pipeline uses the model-specific collection
`okf_chunks_bge_m3`; other models use `okf_chunks_<model>`. Vectors in one
collection must have one dimension, and writes reject mixed dimensions.

Flow: `EmbeddingPipelineService` → `ChromaStore.add_embedded_chunks(...)` →
ChromaDB `upsert`; query callers provide a precomputed query vector. This
module does not extract documents, chunk Markdown, or load embedding models.

代码规模：约 384 行（vector_service Python 文件，包含 CLI、Chroma adapter、配置和注释）。

## ChromaDB CLI

查看当前 BGE-M3 collection 的统计信息：

```bash
python3 -m vector_service.cli stats
```

默认读取项目根目录下的 `vector_db/`，默认 collection 为：

```text
okf_chunks_bge_m3
```

如果使用了其他持久化目录：

```bash
python3 -m vector_service.cli --db-dir /path/to/vector_db stats
```

如果需要检查其他模型的独立 collection：

```bash
python3 -m vector_service.cli --model minilm stats
```

统计输出中的 `count (records)` 是 Chroma 中的 chunk/vector 数量，不是原始文档数量。
批量导入完成后，建议至少检查：

```text
collection_name       是否为 okf_chunks_bge_m3
count (records)       是否大于 0，并与成功处理的 chunk 总数相符
persist_dir           是否为预期的 vector_db 路径
distance_space        是否为 cosine
embedding_dimension   BGE-M3 应为 1024
```

查询示例：

```bash
python3 -m vector_service.cli search "How are newly assigned on-call engineers trained?" --top-k 5
```

`search` 会使用与导入时相同的本地 embedding 模型生成 query vector，再从当前
collection 返回 Top-K chunk。该 CLI 只检查和查询 Chroma，不会重新导入文件或修改
taxonomy。

## 下游集成（rag_service）

在线检索的消费方是 `rag_service`：`graph.retrieve_node` →
`rag_service.retrieval.retrieve()` → `embedding_service.get_embedder()` 编码 +
`ChromaStore.query()` 查询。`rag_service` 只读不写，写入路径仍只有离线导入
（`embedding_service` → `add_embedded_chunks`）。

`query()` 返回的 `VectorSearchResult` 字段（`chunk_id / document_id / title /
heading / source_path / text / distance / rank`）是 rag_service 上下文组装与
sources 输出的契约，修改字段需同步 `rag_service.retrieval`。

注意：`stats()` 的 `embedding_dimension` 曾因为 Chroma `peek()` 返回 numpy 数组、
代码对其做真值判断抛 `ValueError` 被静默吞掉而恒为 `None`；已修复，BGE-M3
collection 应稳定显示 1024。

## 测试

```bash
python3 -m unittest vector_service.test.test_chroma_store -v
```

使用临时目录的 Chroma 实例，覆盖幂等 upsert、query 字段契约、混合维度拒绝，
以及 stats 维度上报的回归；不依赖真实 `vector_db/` 与 embedding 模型。
