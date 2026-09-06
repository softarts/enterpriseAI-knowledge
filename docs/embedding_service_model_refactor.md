# Embedding Service Model Refactor

## 1. 目标与范围

已将 `embedding_service` 重构为模型无关的通用 Embedding Service，并正式支持 BGE-M3 与 MiniLM；同时新增 `document_import` 原始文档转 OKF Service/CLI，并将 chat 导入接入 OKF、embedding 和 ChromaDB 流程。taxonomy 实现保持不变。

## 2. 修改范围与代码量

主要新增/修改代码行数（以完成时 `wc -l` 为准）：`document_import` 约 736 行（其中迁移后的转换实现 616 行）、`embedding_service` Python 文件约 1,138 行、`vector_service` Python 文件约 384 行、`chat_service` 导入服务约 235 行。行数包含注释和 docstring，仅用于规模说明，不是 API 契约。

## 3. 最终目录结构

```text
document_import/
├── __init__.py
├── converter.py
├── legacy_converter.py
├── service.py
├── cli.py
├── requirements.txt
└── README.md

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

## 4. 已完成的模型无关架构

公共 pipeline 通过 `get_embedder()` 获取统一 `Embedder` 协议对象，只调用 `embed_documents()` 与 `embed_query()`。registry 负责选择实现；模型加载、模型名、dimension、normalization 和 encode 参数位于对应模型目录。公共 chunking、storage、search 和数据模型不导入具体模型类，也没有模型-specific pipeline 分支。

## 5. BGE-M3 与 MiniLM

BGE-M3 位于 `embedding_service/bge_m3/`，实际配置为 `BAAI/bge-m3`、1024 维、默认归一化。MiniLM 位于 `embedding_service/minilm/`，沿用现有实现的 `all-MiniLM-L6-v2`、384 维、默认归一化。两者均支持注入 fake model，基础测试不下载模型。

选择方式是 `EMBEDDING_MODEL=bge_m3|minilm`、`get_embedder("...")`，或 importer 的 `--model`。默认模型为 BGE-M3。默认 importer 输出按模型隔离到 `embedding/bge_m3/` 或 `embedding/minilm/`；显式输出目录仍由调用者控制。

## 6. Chunking 实现

公共 `embedding_service/chunker.py` 采用 Markdown-first：解析 heading hierarchy，保存 `heading_path`，heading 行只作为 metadata，不进入正文；空 section 跳过，短 section 保持自然完整，不跨 heading section 合并。超过 1100 token 的 section 才 fallback，顺序为 paragraph、sentence、token-level。target/min/max 为 700/150/1100，fallback overlap 约 12%，不跨 heading。token counter 可注入，默认 counter 与具体模型无关。

实现使用原文 span 而不是 `find()` 定位，因此重复文本的 offsets 仍准确；offsets 是原 Markdown content 的 `(start, end)` 字符范围。chunk 序列和 chunk ID deterministic；ID 包含 document/version/section/span/content hash/chunk version，因此版本变化不会冲突。metadata 包含 chunk/document/version/index/heading path/content/hash/source/token count/chunk version/offsets。

## 7. Embedding、metadata 与 storage

公共 pipeline 构造 `title + " > ".join(heading_path) + content` embedding input，模型自己负责 encode。pipeline 校验返回向量维度，再写入模型标识、实际 dimension、normalization、chunk version 等字段。JSON storage 新增这些字段，同时接受只含旧字段的 JSON，并使用中性默认值；旧 JSON 和旧 embedding 数据没有删除。

新增 `EmbeddingPipelineService` 通过 `vector_service.ChromaStore` 写入 `okf_chunks_bge_m3`；`vector_service` 按模型生成 collection 名称并拒绝单 collection 内的维度混用。旧 `main_import.py --vector-db` 仍保留兼容路径。

## 8. Chat 导入与测试结果

chat_service 默认使用 repository root 下的 `import_data/`：原始上传只进入临时目录，转换后的 OKF 最终保存到 `import_data/okf`，路径可由 `CHAT_IMPORT_ROOT`、`CHAT_IMPORT_STORAGE_DIR`、`CHAT_IMPORT_TEMP_DIR` 和 `CHAT_IMPORT_DB` 配置。确认时 taxonomy 分类逻辑不变，随后执行 BGE-M3 pipeline 和 ChromaDB 写入。

已完成并通过：

- Python 源码 AST/import 检查。
- BGE-M3 与 MiniLM 统一接口 fake-model 检查。
- registry/model switching、dimension validation、normalization。
- heading hierarchy、heading_path、section boundary、short/oversized fallback、overlap、重复文本 offsets、deterministic chunk/ID。
- JSON backward compatibility 与新 metadata round-trip。
- `python3 -m pytest -q tests/test_embedding_service.py tests/test_embedding_import.py tests/test_document_import.py`：13 passed。

未执行真实 BGE-M3/MiniLM 下载集成测试，因此没有对检索效果作结论。直接 `pytest` 不在当前环境 PATH，使用等价的 `python3 -m pytest` 完成验证。

## 9. README 状态

已更新根目录 README、`document_import/README.md`、`embedding_service/README.md`、`vector_service/README.md`、`chat_service/README.md`，包含代码规模、流程和实际接口。

## 10. taxonomy 与外部服务：明确未修改的内容

taxonomy 部分未修改。除本次明确授权的 `vector_service` collection adapter 和 `chat_service` 导入链路外，未修改 doc_service、MCP、API 或其他外部服务。已发现的后续迁移事项如下：

- `doc_service/retrieval/embedding_retriever.py`、`doc_service/api/dependencies.py` 仍导入旧 `embedding_service.embedder.LocalEmbedder`，并按旧 MiniLM 行为读取 embedding 根目录。
- `vector_service/cli.py` 仍使用旧 `LocalEmbedder`，尚未迁移到新的 `EmbeddingPipelineService`/active model API。
- `embedding_service/main_import.py --vector-db` 仍是兼容 CLI 路径，后续可统一改为 pipeline service。

后续迁移需要让外部检索/CLI 选择 active model、读取对应模型目录或 collection，并在 Chroma 层按模型隔离 collection，同时处理旧 MiniLM 数据迁移。这些内容本次尚未完成，也未删除旧数据。

## 11. 已知限制

默认 token counter 是模型无关的确定性近似；需要真实 tokenizer token 数时应由调用者注入对应 counter。现有旧 doc_service/vector_service 调用仍需后续迁移；旧 embedding 数据未删除。真实 BGE-M3 下载集成测试未执行。

## 12. 文档补充

本次后续文档整理已完成：`embedding_service/README.md` 已全量改为中文并补充
chunk 设计理由、代码入口、调用链、流程图、输出格式及 Hit@K/MRR 指标说明；
`document_import/README.md` 补充了转换流程图、Service/CLI 入口和 OKF 中间格式设计；
`chat_service/README.md` 集中了 chat 对话、导入、配置、存储和 API 说明；根目录
README 仅保留文档 ingestion 的 high-level 流程和各子模块链接。
