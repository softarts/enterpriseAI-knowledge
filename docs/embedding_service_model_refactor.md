# Embedding Service Model Refactor

## 1. 目标与范围

已将 `embedding_service` 重构为模型无关的通用 Embedding Service，并正式支持 BGE-M3 与 MiniLM。本次只修改了 `embedding_service`、其直接相关测试、README、依赖文件和本报告；没有修改 vector_service、doc_service、MCP、API 或其他外部服务。

## 2. 最终目录结构

```text
embedding_service/
├── __init__.py
├── config.py
├── models.py
├── models_registry.py
├── embedder.py
├── chunker.py
├── storage.py
├── search.py
├── service.py
├── main_import.py
├── requirements.txt
├── README.md
├── bge_m3/
│   ├── __init__.py
│   └── embedder.py
└── minilm/
    ├── __init__.py
    └── embedder.py
```

## 3. 已完成的模型无关架构

公共 pipeline 通过 `get_embedder()` 获取统一 `Embedder` 协议对象，只调用 `embed_documents()` 与 `embed_query()`。registry 负责选择实现；模型加载、模型名、dimension、normalization 和 encode 参数位于对应模型目录。公共 chunking、storage、search 和数据模型不导入具体模型类，也没有模型-specific pipeline 分支。

## 4. BGE-M3 与 MiniLM

BGE-M3 位于 `embedding_service/bge_m3/`，实际配置为 `BAAI/bge-m3`、1024 维、默认归一化。MiniLM 位于 `embedding_service/minilm/`，沿用现有实现的 `all-MiniLM-L6-v2`、384 维、默认归一化。两者均支持注入 fake model，基础测试不下载模型。

选择方式是 `EMBEDDING_MODEL=bge_m3|minilm`、`get_embedder("...")`，或 importer 的 `--model`。默认模型为 BGE-M3。默认 importer 输出按模型隔离到 `embedding/bge_m3/` 或 `embedding/minilm/`；显式输出目录仍由调用者控制。

## 5. Chunking 实现

公共 `embedding_service/chunker.py` 采用 Markdown-first：解析 heading hierarchy，保存 `heading_path`，heading 行只作为 metadata，不进入正文；空 section 跳过，短 section 保持自然完整，不跨 heading section 合并。超过 1100 token 的 section 才 fallback，顺序为 paragraph、sentence、token-level。target/min/max 为 700/150/1100，fallback overlap 约 12%，不跨 heading。token counter 可注入，默认 counter 与具体模型无关。

实现使用原文 span 而不是 `find()` 定位，因此重复文本的 offsets 仍准确；offsets 是原 Markdown content 的 `(start, end)` 字符范围。chunk 序列和 chunk ID deterministic；ID 包含 document/version/section/span/content hash/chunk version，因此版本变化不会冲突。metadata 包含 chunk/document/version/index/heading path/content/hash/source/token count/chunk version/offsets。

## 6. Embedding、metadata 与 storage

公共 pipeline 构造 `title + " > ".join(heading_path) + content` embedding input，模型自己负责 encode。pipeline 校验返回向量维度，再写入模型标识、实际 dimension、normalization、chunk version 等字段。JSON storage 新增这些字段，同时接受只含旧字段的 JSON，并使用中性默认值；旧 JSON 和旧 embedding 数据没有删除。

本次 `embedding_service` 内没有 Chroma adapter。已有可选 `--vector-db` 仍委托外部 `vector_service`，因此没有在外部服务中实现新的 collection 隔离。

## 7. 测试结果

已完成并通过：

- Python 源码 AST/import 检查。
- BGE-M3 与 MiniLM 统一接口 fake-model 检查。
- registry/model switching、dimension validation、normalization。
- heading hierarchy、heading_path、section boundary、short/oversized fallback、overlap、重复文本 offsets、deterministic chunk/ID。
- JSON backward compatibility 与新 metadata round-trip。
- `python3 -m pytest -q tests/test_embedding_service.py tests/test_embedding_import.py`：11 passed。

未执行真实 BGE-M3/MiniLM 下载集成测试，因此没有对检索效果作结论。直接 `pytest` 不在当前环境 PATH，使用等价的 `python3 -m pytest` 完成验证。

## 8. README 状态

`embedding_service/README.md` 已更新，描述实际的 chunking、fallback、overlap、offsets、chunk version、统一接口、两个模型、输入构造、batch size、normalization、dimension validation、模型切换和 JSON 兼容性。

## 9. 外部服务：明确未修改的内容

未修改 vector_service、doc_service、MCP、API 或其他外部服务。已发现的后续迁移事项如下：

- `doc_service/retrieval/embedding_retriever.py`、`doc_service/api/dependencies.py` 仍导入旧 `embedding_service.embedder.LocalEmbedder`，并按旧 MiniLM 行为读取 embedding 根目录。
- `vector_service/cli.py` 仍使用旧 `LocalEmbedder`；`vector_service/chroma_store.py` 仍控制旧 collection 行为。
- `embedding_service/main_import.py --vector-db` 仍委托上述旧 Chroma adapter。

后续迁移需要让外部检索/CLI 选择 active model、读取对应模型目录或 collection，并在 Chroma 层按模型隔离 collection，同时处理旧 MiniLM 数据迁移。这些内容本次尚未完成，也未删除旧数据。

## 10. 已知限制

默认 token counter 是模型无关的确定性近似；需要真实 tokenizer token 数时应由调用者注入对应 counter。embedding_service 内没有新的 Chroma adapter，collection 隔离需要后续外部 vector_service 迁移完成。
