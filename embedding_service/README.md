# embedding_service

`embedding_service` 是模型无关的本地 Embedding pipeline。它接收 OKF 文档，完成
Markdown-first chunking、Embedding、metadata 组装，并可将结果交给
`vector_service` 写入 ChromaDB。

代码规模：约 1,138 行（根目录 Python 文件，包含公共 pipeline、chunker、storage、
search、注释和 docstring；模型实现位于 `bge_m3/` 与 `minilm/`）。

## 一、整体流程

```text
OKF 文档
   │
   ▼
EmbeddingPipelineService.process_okf_file()
   │
   ├── 解析 OKF document metadata + Markdown body
   ├── chunk_document()       （公共、模型无关）
   ├── get_embedder("bge_m3") （registry 选择模型）
   ├── embed_documents()      （模型目录中的实现）
   ├── dimension / metadata 校验
   └── ChromaStore.add_embedded_chunks() 或 JSON storage
```

主要入口：

- Service API：`embedding_service/pipeline.py:EmbeddingPipelineService`
- 单文件入口：`EmbeddingPipelineService.process_okf_file(path)`
- 已解析对象入口：`EmbeddingPipelineService.process_document(document)`
- 模型工厂：`embedding_service/embedder.py:get_embedder()`
- CLI 兼容入口：`embedding_service/main_import.py`

## 二、Chunk 设计

### 为什么采用 Markdown-first

企业文档通常有标题、章节和子章节。若直接按固定字符数切整篇文档，会把一个
章节拆开，也可能把两个无关章节合并，导致检索结果缺少上下文或产生主题污染。
因此 chunker 先识别 Markdown heading，再以 section 为边界进行处理。

Chunker 的公共实现位于 `embedding_service/chunker.py:chunk_document()`，不依赖
BGE-M3 或 MiniLM。token count 默认使用 `default_token_count()` 的确定性近似；如果
调用方需要真实 tokenizer，可以通过 `tokenizer` 参数注入计数函数。

### Chunk 流程

```text
Markdown body
   │
   ▼
识别 # ~ ###### heading
   │
   ▼
建立 heading hierarchy / heading_path
   │
   ▼
按 heading section 分组，heading 行不进入 content
   │
   ├── section <= max_tokens ──► 保持完整，直接生成一个 chunk
   │
   └── section > max_tokens
          │
          ├── paragraph fallback
          ├── paragraph 仍过大 → sentence fallback
          └── sentence 仍过大 → token-level fallback
                    │
                    ▼
              按 target packing + 约 12% overlap
```

### 具体规则

- `target_tokens = 700`。
- `min_tokens = 150`，但短 section 是自然完整内容时不会被强行补齐或拆分。
- `max_tokens = 1100`。
- 只有超过 `max_tokens` 的 section 才进入 fallback。
- fallback 优先保持 paragraph，其次 sentence，最后才按 token 切分。
- overlap 只用于 oversized section 的 fallback，约为 `1100 * 0.12`。
- overlap 不会跨越 heading，因此不会把相邻章节混在一起。
- 空 section 跳过；第一个 heading 之前的正文作为根 section。
- heading hierarchy 使用栈维护，例如 `# A`、`## B`、`### C` 的路径为
  `("A", "B", "C")`。
- `heading_path` 保存完整路径，`heading` 保存当前 section 的最后一级标题。

### offsets、重复文本和 deterministic ID

切分时保存原始 Markdown 的字符 span，而不是使用 `text.find()` 反查文本位置，
因此文档中出现重复段落时 offsets 仍然准确。最终满足：

```python
original_content[start:end] == chunk.content
```

chunk ID 由 document ID、version、heading path、原文 span、content hash 和
`chunk_version` 共同计算。同样的 document/version/input 会得到完全相同的 chunk
序列和 ID；version 改变时不会与旧版本冲突。

### Chunk metadata

每个 chunk 至少包含：

```text
chunk_id, document_id, version, chunk_index, heading_path,
content, content_hash, source_path, token_count, chunk_version, offsets
```

对应数据结构位于 `embedding_service/chunker.py:Chunk`，Embedding 后的记录位于
`embedding_service/models.py:EmbeddedChunk`。

### Chunk 配置位置

公共默认值位于 `embedding_service/config.py`：

```text
CHUNK_TARGET_TOKENS = 700
CHUNK_MIN_TOKENS    = 150
CHUNK_MAX_TOKENS    = 1100
CHUNK_OVERLAP_RATIO = 0.12
```

当前 `EmbeddingPipelineService` 使用 `chunk_document()` 的默认值；若未来需要
外部化配置，可以在 pipeline 层传入这些参数，不需要修改模型实现。

## 三、Embedding 入口与过程

### 入口函数

正式 pipeline 入口是：

```python
EmbeddingPipelineService.process_okf_file(file_path)
```

它位于 `embedding_service/pipeline.py`。如果调用方已经通过 OKF repository
解析出 document，也可以调用 `process_document(document)`。

### 调用链

```text
process_okf_file(path)
   │
   ├── document_import.parse_okf_file()
   │
   └── process_document(document)
          │
          ├── chunk_document(...)
          │      └── 返回 Chunk[]
          │
          ├── 构造 embedding input
          │      title + " > ".join(heading_path) + content
          │
          ├── self.embedder.embed_documents(texts)
          │      └── BgeM3Embedder / MiniLMEmbedder
          │
          ├── 校验 vector 数量与 dimension
          │
          ├── 构造 EmbeddedChunk[]
          │
          └── vector_store.add_embedded_chunks()
```

`get_embedder()` 位于 `embedder.py`，registry 位于 `models_registry.py`。模型名称、
模型加载和 encode 行为分别位于：

- `bge_m3/embedder.py:BgeM3Embedder`
- `minilm/embedder.py:MiniLMEmbedder`

BGE-M3 默认模型为 `BAAI/bge-m3`、1024 维；MiniLM 沿用现有的
`all-MiniLM-L6-v2`、384 维。两个模型都默认启用 normalization，默认 batch size
为 32，并且采用 lazy loading，基础测试不下载模型。

### 模型选择

```python
get_embedder("bge_m3")
get_embedder("minilm")
```

或设置：

```bash
export EMBEDDING_MODEL=minilm
python3 embedding_service/main_import.py --model minilm
```

默认 importer 输出目录按模型隔离，例如 `embedding/bge_m3/` 和
`embedding/minilm/`。模型切换不会把不同维度的向量写入同一个默认目录或 collection。

## 四、输出文件格式

JSON storage 由 `embedding_service/storage.py` 负责。每个文档对应一个 JSON 数组，
每一项是一个 `EmbeddedChunk`：

```json
[
  {
    "chunk_id": "doc-chunk-000-abc123",
    "document_id": "doc",
    "title": "示例文档",
    "heading": "概述",
    "heading_path": ["示例文档", "概述"],
    "content": "正文内容",
    "content_hash": "sha256...",
    "source_path": "source.txt",
    "version": "v1",
    "chunk_index": 0,
    "token_count": 120,
    "chunk_version": "v1",
    "offsets": [12, 18],
    "embedding_model": "BAAI/bge-m3",
    "embedding_dimension": 1024,
    "normalized": true,
    "embedding": [0.0123, -0.0456]
  }
]
```

旧 JSON 如果缺少新增字段仍可读取；缺少的信息使用空值、空 tuple 或默认
`chunk_version`，不会伪造原始 metadata。旧数据不会被删除。

如果启用 vector store，`vector_service.ChromaStore` 使用模型独立 collection：

```text
okf_chunks_bge_m3
okf_chunks_minilm
```

## 五、检索评估指标

评估工具位于 `embedding_service/evaluation/evaluate_retrieval.py`，评估 query 和
标注相关文档之间的检索排名。当前评估数据位于 `evaluation/`。

### Hit@K

`Hit@K` 表示前 K 个结果中是否至少有一个正确结果：

```text
Hit@K = 命中至少一个相关文档的 query 数 / query 总数
```

- Hit@1：第一名是否正确，最严格，适合衡量首条结果质量。
- Hit@3：前三名是否出现正确结果，适合用户会查看少量结果的场景。
- Hit@5：前五名是否出现正确结果，适合候选召回能力评估。

### MRR

MRR（Mean Reciprocal Rank，平均倒数排名）关注第一个正确结果出现的位置：

```text
MRR = 平均值(1 / 第一个相关结果的排名)
```

第一名命中贡献 1，第二名贡献 0.5，第三名贡献约 0.333。若 query 没有命中，
贡献为 0。MRR 适合衡量用户需要向下浏览多少结果才能看到第一个正确答案。

### 指标的用途和限制

- Hit@K 适合判断“候选集合是否召回了正确文档”。
- MRR 适合判断“正确文档排得是否足够靠前”。
- 多个指标需要一起看：Hit@5 高但 MRR 低，可能说明能召回但排序靠后。
- 评估指标依赖 query 标注和测试语料，不能单独证明某个模型在所有业务文档上更好。
- 当前报告中的数值只代表对应评估数据和配置，不应外推为 BGE-M3 相对 MiniLM 的
  普遍效果结论。

## 六、测试和命令

```bash
python3 embedding_service/main_import.py --model bge_m3
python3 embedding_service/main_import.py --model minilm
python3 embedding_service/validate.py
python3 -m pytest -q tests/test_embedding_service.py tests/test_embedding_import.py
```

基础测试使用 fake model，覆盖统一接口、模型 registry、dimension validation、
heading hierarchy、fallback、overlap、offsets、deterministic ID 和 JSON backward
compatibility，不依赖网络下载真实模型。
