# Chat Service Import Flow

The document import API stores its converted OKF output under the repository
root `import_data/okf` by default. The root is configurable with
`CHAT_IMPORT_ROOT`; `CHAT_IMPORT_STORAGE_DIR`, `CHAT_IMPORT_TEMP_DIR`, and
`CHAT_IMPORT_DB` remain independently configurable.

Flow: upload → temporary raw file → `DocumentImportService` conversion → OKF
temporary file and taxonomy classification → user confirmation →
`EmbeddingPipelineService` with BGE-M3 → ChromaDB collection
`okf_chunks_bge_m3` → finalized OKF file. Taxonomy classification remains the
existing implementation and is not changed by this flow.

代码规模：本次修改的导入服务核心约 235 行；chat_service 其他功能未重构。

## 服务职责与代码入口

`chat_service` 是 FastAPI 后端和 React 前端 playground。对话入口是
`chat_service/api/routes_chat.py` 的 `POST /api/chat`，由
`services/chat_service.py:ChatService.ask()` 编排 request → LLM → response，
`trace.py:TraceBuilder` 记录执行步骤；前端 `frontend/src/App.jsx` 在浏览器内存中
维护消息历史，`ChatWindow.jsx` 渲染消息，`TracePanel.jsx` 渲染 trace。

LLM 配置在 `chat_service/llm_config.yaml`，环境变量可以覆盖模型和 token 上限；
真实 token 只从环境变量读取。启动方式是 `python -m chat_service.run`，前端位于
`chat_service/frontend/`。

## 文档导入流程

```text
Browser
  -> POST /api/documents/import
  -> routes_import.import_document()
  -> ImportService.import_file()
       校验上传 -> ImportStorage.save_temp()
       -> DocumentImportService.convert()
       -> 暂存 OKF + TaxonomyClassifier.classify_text()
       -> ImportDB 写入 pending
  -> 用户确认
  -> POST /api/documents/import/{id}/confirm
  -> EmbeddingPipelineService.process_okf_file()
       chunk_document() -> get_embedder("bge_m3")
       -> ChromaStore.add_embedded_chunks()
  -> ImportStorage.finalize()
       -> 根目录 import_data/okf/{documents/shard/...}.yaml
  -> ImportDB 更新 imported
```

API 入口在 `api/routes_import.py`：上传返回 `pending`，查询使用
`GET /api/documents/import/{id}`，确认使用 `POST /api/documents/import/{id}/confirm`。
确认时先完成 embedding 和 ChromaDB 写入，再把转换后的 OKF 文件从临时目录移动到
永久目录；原始上传文件不会作为最终文档保存。失败时保持 pending，便于重试。

### 存储和配置

默认配置位于 `chat_service/config.py:Settings`：

| 配置 | 默认值 | 作用 |
|---|---|---|
| `CHAT_IMPORT_ROOT` | 根目录 `import_data/` | 导入数据总目录 |
| `CHAT_IMPORT_TEMP_DIR` | `import_data/temp/` | 暂存原始上传和 OKF |
| `CHAT_IMPORT_STORAGE_DIR` | `import_data/okf/` | 最终 OKF 文件目录 |
| `CHAT_IMPORT_DB` | `import_data/documents.db` | 导入 metadata SQLite |
| `CHAT_IMPORT_MAX_MB` | `25` | 上传大小限制 |

`ImportStorage` 使用 UUID 分片目录，并通过 `stored_filename` 区分用户原始文件名
和最终 `.yaml` 文件名。`ImportDB` 保存分类结果、taxonomy version、状态、文件大小、
原始文件名和 OKF 存储路径。

### Taxonomy 在导入链路中的位置

taxonomy 仍由 `kb_classifier.taxonomy_classifier.classify.py:TaxonomyClassifier`
负责。`ImportService._get_classifier()` 懒加载分类器，调用
`classify_text(title, body)`，再把 `to_okf_metadata()` 返回的分类信息写入 SQLite。
本次没有修改 taxonomy 的版本、阈值或匹配算法。

### 相关文件

| 文件 | 作用 |
|---|---|
| `api/routes_import.py` | 导入 API 路由 |
| `services/import_service.py` | 上传、转换、分类、确认编排 |
| `import_storage.py` | 原始上传暂存和 OKF 最终文件存储 |
| `import_db.py` | 导入状态与分类 metadata |
| `config.py` | `import_data` 根目录和环境变量配置 |
| `../document_import/` | 原始文档 → OKF 的独立 Service/CLI |
| `../embedding_service/pipeline.py` | OKF → chunk → embedding → vector store |
| `../vector_service/chroma_store.py` | ChromaDB collection 写入 |

## 对话 Playground

对话流程是：

```text
Browser App.jsx
  -> POST /api/chat {question}
  -> routes_chat.py
  -> ChatService.ask()
  -> HuggingFaceLLM.chat()
  -> answer + trace
  -> ChatWindow.jsx / TracePanel.jsx
```

后端是无状态的，单次请求只接收当前 `question`；对话历史由
`frontend/src/App.jsx` 的 React state 保存在浏览器内存，刷新页面会清空历史。消息
列表由 `ChatWindow.jsx` 渲染，单条消息由 `Message.jsx` 渲染，后端真实执行步骤由
`TracePanel.jsx` 渲染。

主要 API：

| 方法 | 路径 | 作用 |
|---|---|---|
| `GET` | `/api/health` | 服务状态和 token 是否已配置 |
| `POST` | `/api/chat` | 单轮问题，返回 answer 和 trace |
| `POST` | `/api/documents/import` | 上传并转换、分类，返回 pending |
| `GET` | `/api/documents/import/{id}` | 查询导入记录 |
| `POST` | `/api/documents/import/{id}/confirm` | 执行 embedding、Chroma 写入并完成 OKF 入库 |
| `GET` | `/api/taxonomy` | 只读 taxonomy 树 |
| `GET` | `/api/documents` | 分页列出已导入文档 |
| `GET` | `/api/documents/{id}/preview` | 预览 OKF 的正文 metadata |

LLM 的非机密配置在 `chat_service/llm_config.yaml`，例如 provider、model、
`max_tokens` 和 `${HF_TOKEN}` 引用。真实 token 只从环境变量读取。`max_tokens` 只
限制 completion，不限制 prompt；如果 trace 的 `finish_reason` 为 `length`，表示
输出触达上限，可能被截断。配置优先级为环境变量 > YAML > 内置默认值。

后端启动：

```bash
export HF_TOKEN=hf_xxx
python -m chat_service.run
```

前端启动：

```bash
cd chat_service/frontend
npm install
npm run dev
```

## 当前边界

taxonomy 仍由 `kb_classifier` 提供，chat_service 不修改 taxonomy 版本、阈值或匹配
算法。文档导入已接入 embedding 和 ChromaDB；对话 Ask 流程仍是单轮 LLM 调用，
RAG context 组装尚未接入 `/api/chat`。
