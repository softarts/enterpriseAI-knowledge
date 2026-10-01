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

## 批量导入任务

批量导入提供独立的任务页面和独立 worker 进程，不使用 Celery、Redis 或其他外部
任务队列。任务状态保存在现有 SQLite 数据库的 `import_tasks` 和
`import_task_files` 两张表中，因此用户离开页面后任务仍可继续，重新进入任务页面
可以恢复状态。

### 三个 Stage

```text
Stage 1 上传
  目录拖拽 / 目录选择，或服务端 evaluation manifest CLI
  -> 文件列表 + 相对路径登记
  -> import_data/temp/tasks/{task_id}/
  -> 所有文件进入 uploaded

Stage 2 处理
  独立 batch_worker 进程
  -> DocumentImportService.convert()
  -> TaxonomyClassifier.classify_text()
  -> EmbeddingPipelineService.process_okf_file()
  -> ChromaStore(okf_chunks_bge_m3)
  -> OKF 移动到 import_data/okf/tasks/{task_id}/

Stage 3 完成
  -> 所有文件进入 completed 或 failed
  -> 任务页面展示分类、OKF 路径、状态和错误
```

Stage 1 和 Stage 2 都记录已完成数量、总数量和百分比。Stage 2 每处理完一个文件
就更新任务表；单文件失败只标记该文件为 `failed`，不会中断其他文件。

### API

| 方法 | 路径 | 作用 |
|---|---|---|
| `POST` | `/api/tasks/batch-import` | 上传一批文件并创建任务 |
| `GET` | `/api/tasks` | 查询任务列表 |
| `GET` | `/api/tasks/{task_id}` | 查询任务、三个阶段和文件明细 |
| `POST` | `/api/tasks/{task_id}/retry` | 手动重新执行失败文件 |

上传接口接收 multipart `files` 和 JSON 字符串 `relative_paths`。前端
`BatchUploadArea.jsx` 使用目录选择和目录拖拽收集文件；`TaskPage.jsx` 每 2.5 秒轮询
任务详情，不依赖页面持续打开。

### Evaluation source manifest CLI

`embedding_service/evaluation/evaluation_queries.json` 是 query ground truth，不直接作为
上传文件。`document_import.evaluation_manifest` 会提取其中唯一的
`expected_source_path`，生成固定的 `embedding_service/evaluation/evaluation_sources.json`。
当前 manifest 覆盖 20 条 query 和 8 个源文件；源文件默认位于 `all_documents/`，但 CLI
通过参数接收 source root，不在代码中硬编码绝对路径。

生成清单：

```bash
python -m document_import.evaluation_manifest \
  --queries embedding_service/evaluation/evaluation_queries.json \
  --source-root all_documents \
  --output embedding_service/evaluation/evaluation_sources.json
```

在 server 文件系统上创建现有批量任务，不经过浏览器和 multipart 上传：

```bash
python -m chat_service.server_import_cli \
  --manifest embedding_service/evaluation/evaluation_sources.json \
  --wait
```

manifest 的 `source_path` 使用绝对路径，`source_path_key` 作为稳定的逻辑来源标识。
使用 `--dry-run` 只校验文件、扩展名和 content hash，不创建任务；`--wait` 等待独立
worker 完成并返回最终统计。CLI 只负责读取 server-local 文件并调用
`BatchImportService.create_task_from_paths()`；后续仍由同一个独立 worker、SQLite 任务表
和 Tasks 页面处理。

### Worker 执行方式

API 创建任务后启动：

```bash
python -m chat_service.batch_worker --task-id <task_id>
```

worker 代码位于 `chat_service/batch_worker.py`，处理逻辑位于
`services/batch_import_service.py:BatchImportWorker`。worker 是独立进程，但任务表是
唯一状态源；不考虑服务重启后的自动恢复，失败任务通过任务页面手动重试。

### 数据表

`import_tasks` 保存批次级状态：`task_id`、`status`、`stage`、总文件数、已上传数、
已处理数、失败数、错误和时间字段。

`import_task_files` 保存文件级状态：`file_id`、相对路径、临时路径、OKF 路径、最终
存储路径、taxonomy 分类、错误、重试次数、原始文件 SHA-256 和状态。

当前任务状态包括：`queued`、`running`、`completed`；文件状态包括
`uploaded`、`converting`、`embedding`、`completed`、`duplicate`、`failed`。

### 幂等和重复执行

- 已完成文件在 worker 重复运行时跳过。
- 失败文件通过 `POST /api/tasks/{task_id}/retry` 重置为 `uploaded`。
- ChromaDB 使用稳定 chunk ID 做 upsert。
- 后端只按原始文件字节计算 SHA-256 去重，不比较文件路径、文件名或标题。
- 重复文件在 OKF 转换、taxonomy 和 embedding 之前标记为 `duplicate` 并跳过。
- 批量任务中重复文件计入已处理数量，不阻塞其他文件。
- 一个批次不依赖前端页面，允许 scheduler 直接调用 worker 命令。
- 暂不实现服务重启后的自动恢复、并发锁和外部任务队列。

### 内容去重

单文件和批量导入都在后端计算原始上传内容的 SHA-256，并查询
`documents_import.content_hash`。路径、原始文件名、标题和解析后的文本都不参与
本次重复判断。已存在的内容直接返回已有导入记录，或者在批量任务中将文件标记为
`duplicate`；不会再次转换 OKF、执行 taxonomy、生成 embedding 或写入 ChromaDB。

本次按“内容相同就是重复文件”处理，因此不同路径下的相同文件也只保留一份向量数据。
数据库仍保留批量任务中的重复文件状态，便于审计本次导入尝试。
当前采用方案 A：新内容使用原始文件的完整 SHA-256 作为稳定的 `document_id` 写入
OKF。这样相同字节内容会得到相同的 document/chunk identity；不同内容会得到新的
document ID，旧内容的 chunk ID 和 embedding 不会被覆盖。文件实际保存名不再承担
document identity，必要时可以使用 content hash 作为保存名的一部分。

### 后续文档版本血缘关系（方案 B，暂未实现）

当前文件内容发生变化时，按方案 A 作为新内容导入，不尝试删除或替换旧内容。
如果将来需要识别“同一逻辑文件的不同版本”，可以使用 `source_path_key` 作为
候选文档身份，再结合以下信号进行确认：

- `source_path_key`：判断是否来自同一逻辑源文件；
- title 和正文内容的 embedding 相似度：判断标题和内容是否具有版本连续性；
- taxonomy 分类结果：判断文档所属主题和业务分类是否一致；
- 原始文件名、来源和时间等 metadata：作为辅助证据，不作为唯一判据。

其中，`source_path_key` 适合做候选分组，但不能单独证明两个文件是同一版本链；
embedding 和 taxonomy 也应作为组合信号，而不是单独决定版本关系。未来可以增加
`lineage_id`、`parent_document_id`、版本时间、相似度分数和 `is_current` 等字段，
并明确检索默认返回全部版本还是仅当前版本。

血缘字段应作为 metadata 保存，不应拼接进 chunk embedding 文本。启用版本替换前，
仍应保留旧文件的 OKF、chunk 和 embedding，并通过独立维护命令决定何时清理旧数据。

### 前端任务页面

左侧任务列表分为“运行中”和“已完成”；点击任务后右侧显示四个统计信息和三个可展开
Stage。点击每个 Stage 可以查看该阶段进度、文件计数和文件级状态。Stage 3 表格已经
展示文件、状态、分类和存储位置；预览、修改分类和单文件重新处理入口暂时只保留后续
扩展位置，当前不提供接口。

### 相关代码规模

本次批量任务相关代码约 650 行（包含后端任务 service/worker、SQLite 状态表、任务
API、前端任务页面、目录上传组件和样式；包含注释和 docstring）。测试用例将在下一
阶段补充。

## 服务职责与代码入口

`chat_service` 是 FastAPI 后端和 React 前端 playground。对话入口是
`chat_service/api/routes_chat.py` 的 `POST /api/chat`，由
`chat_service/services/chat/chat_service.py:ChatService.ask()` 编排 request →
Checkpointer-backed LLM → response，`trace.py:TraceBuilder` 记录执行步骤；前端
`frontend/src/App.jsx` 在浏览器内存中维护消息历史，`ChatWindow.jsx` 渲染消息，
`TracePanel.jsx` 展示本次请求的问句与回答以及各执行步骤。Trace 按请求独立生成，
不会自动拼接同一 conversation 的前序问答。

Chat 与 Ask 共用 `qa_service.llm_client.get_llm()` 及 `LLM_API_KEY`、
`LLM_BASE_URL`、`LLM_MODEL` 等全局环境配置。启动方式是 `python -m chat_service.run`，前端位于
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

Chat server/CORS 设置位于 `chat_service/services/chat/config.py:Settings`；文档导入和维护工具使用独立的 `chat_service/import_config.py`：

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
  -> POST /api/chat {question} + X-Conversation-Id
  -> routes_chat.py
  -> ChatService.ask()
  -> LangGraph agent + Checkpointer(thread_id)
  -> qa_service.llm_client.get_llm()
  -> answer + trace
  -> ChatWindow.jsx / TracePanel.jsx
```

前端为每个浏览器 tab 在 `sessionStorage` 生成并复用 `X-Conversation-Id`；后端
使用该值作为 LangGraph `thread_id`，通过进程级 `MemorySaver` 自动恢复并保存消息。
不同 thread 不共享历史；进程重启后历史清空。`/api/chat` 是纯聊天，不执行 RAG。
消息列表由 `ChatWindow.jsx` 渲染，单条消息由 `Message.jsx` 渲染，后端执行步骤由
`TracePanel.jsx` 渲染。

主要 API：

| 方法 | 路径 | 作用 |
|---|---|---|
| `GET` | `/api/health` | 服务状态和共享 LLM 配置是否完整 |
| `POST` | `/api/chat` | 纯聊天；需要 `X-Conversation-Id`，返回 answer 和 trace |
| `POST` | `/api/chat/stream` | SSE 流式聊天（见下文「流式对话」） |
| `POST` | `/api/documents/import` | 上传并转换、分类，返回 pending |
| `GET` | `/api/documents/import/{id}` | 查询导入记录 |
| `POST` | `/api/documents/import/{id}/confirm` | 执行 embedding、Chroma 写入并完成 OKF 入库 |
| `GET` | `/api/taxonomy` | 只读 taxonomy 树 |
| `GET` | `/api/documents` | 分页列出已导入文档 |
| `GET` | `/api/documents/{id}/preview` | 预览 OKF 的正文 metadata |

LLM 直接使用 `qa_service` 的全局 OpenAI-compatible 配置：`LLM_BASE_URL`、
`LLM_MODEL`、`LLM_API_KEY`、`LLM_MAX_TOKENS` 和 `LLM_ENABLE_THINKING`。`/api/health`
只返回配置完整性布尔值，不返回密钥。

## 流式对话（SSE）

`/api/chat/stream` 以 SSE 推送一次问答的完整过程。因为要带 POST body 和自定义
header，前端用 `fetch` + `ReadableStream` 手动解析 SSE，而不是 `EventSource`。

```text
POST /api/chat/stream  {question, token_scope}
  -> ChatStreamService.stream_turn()
  -> graph.astream(stream_mode=["custom","messages","updates"])
  -> StreamEventMapper -> StreamEvent -> "data: {json}\n\n"
```

### 事件协议

每帧是一个 JSON 对象，`type` 决定前端分流：

```jsonc
{"type":"token","text":"你好","turn":1}
{"type":"tool_call","id":"call_1","name":"web_search","args":{"query":"news"}}
{"type":"tool_result","id":"call_1","name":"web_search","status":"ok","content":"..."}
{"type":"node_start","node":"agent"}
{"type":"interrupt","thread_id":"conv-1","question":"即将调用外部工具 web_search，是否继续？","resume_key":"conv-1:call_1","tools":[...]}
{"type":"done","usage":{"input_tokens":812,"output_tokens":96},"finish_reason":"stop"}
{"type":"error","message":"...","code":"upstream"}
```

`finish_reason` 为 `interrupt` 表示本轮因 HITL 暂停（此时 `usage` 为 null）；
流在 `done` 事件后结束，前端可无条件清除 loading 状态。

### 三路 stream mode 的分工

LangGraph 的 token 有两条限制，因此需要同时消费三个通道：

| 通道 | 提供 | 说明 |
|---|---|---|
| `custom` | token、tool_call | 节点内 LLM 的 chunk **不会**冒泡为 `on_chat_model_stream`，只能由 agent 节点用 `get_stream_writer()` 主动写出 |
| `messages` | node_start | `(message, metadata)` 元组，`metadata["langgraph_node"]` 是节点名 |
| `updates` | interrupt、tool_result | 节点级 state delta；暂停运行时顶层出现 `__interrupt__` 键 |

`tool_result` 与 `usage` 不在流式载荷里：前者从 `updates` 通道当轮收集的
`ToolMessage` 生成（不读 checkpoint，避免重发历史轮次的工具结果），后者取自
`updates` 通道最终 AIMessage 的 `usage_metadata`。

`token_scope`：`all`（默认）立即转发每轮 token；`final` 先缓冲，只有在没发生工具
调用时才在结束时输出，避免把"决定调工具"那轮的中间文本暴露给用户。

### HITL（人工确认）

`langchain_agent` 图在 `agent` 与 `tools` 之间有 `hitl_gate` 节点，对
`HITL_TOOLS`（默认 `web_search`）调用 `interrupt()`。默认开启，可用
`HITL_ENABLED=false` 关闭。

- 首轮流到 `HITL_TOOLS` 里的工具时暂停，发送 `interrupt` 事件，**工具不执行**
- 前端确认后调 `POST /api/chat/resume`（body `{"resume": true|false}`），
  后端用 `Command(resume=...)` 从同一 checkpoint 的中断点继续，不重复已发出的
  LLM 调用
- 中断状态存在 Checkpointer 中；进程重启会丢失（当前为进程内 `MemorySaver`）

`web_search` 默认**自动执行、不弹确认框**（`WEB_SEARCH_AUTO_EXECUTE=true`，
见 `langchain_agent/app/config.py`）：`hitl_gate_node` 在决定哪些 pending
tool_call 需要确认时，会对 `name == "web_search"` 且该开关为真的调用直接放行。
把 `WEB_SEARCH_AUTO_EXECUTE=false` 可以恢复“每次搜索都要手工确认”的旧行为，
而不影响 `HITL_TOOLS` 里其他工具（如果以后加进去）的确认逻辑。

### Agent 最大步数（防止死循环）

图在 `agent -> hitl_gate -> tools -> agent` 之间循环，直到模型不再请求工具调用。
如果模型反复用越来越离谱的 query 调同一个工具（例如不断把 `web_search` 的
`query` 参数越拼越长），图会无限循环下去。两个入口各有一个独立的步数上限，
超限时 LangGraph 抛 `GraphRecursionError`，由入口捕获并转成友好提示（流式是
`{"type":"error","code":"recursion_limit"}` SSE 事件，非流式是一句中文提示），
不会让请求挂起：

| 环境变量 | 默认值 | 作用入口 |
|---|---|---|
| `AGENT_MAX_STEPS_SYNC` | `10` | `/api/chat`（`langchain_agent/app/runtime.py` 的 `GRAPH_RECURSION_LIMIT`） |
| `AGENT_MAX_STEPS_STREAM` | `25` | `/api/chat/stream`（`chat_service/services/chat/chat_stream.py` 的 `RECURSION_LIMIT`） |

类似 Copilot VS Code 插件里对一次请求的最大工具调用轮数做硬性限制。

### 流式相关 API

| 方法 | 路径 | 作用 |
|---|---|---|
| `POST` | `/api/chat/stream` | SSE 流式一次问答 |
| `POST` | `/api/chat/resume` | 恢复被 HITL 暂停的一轮 |
| `POST` | `/api/chat/cancel` | 按 `X-Conversation-Id` 取消服务端正在执行的图任务 |

停止生成是双端的：前端 `AbortController.abort()` 断开连接，后端路由在检测到
客户端断开或收到 `/api/chat/cancel` 时取消 `asyncio.Task`，立即停止 LLM 调用。
重新生成只需带同一个 `X-Conversation-Id` 重发 `/api/chat/stream`，历史由
Checkpointer 恢复。

前端事件分流见 `src/api/chatApi.js`（`askQuestionStream` / `resumeStream` /
`cancelStream`）与 `src/App.jsx` 的 `handleStreamEvent`：token 追加渲染到聊天
气泡，interrupt 弹确认框，done 结束 loading。

`tool_call`/`tool_result` **不**渲染在聊天窗口里——聊天窗口只显示最终回答
（以及 error 消息和 HITL 确认框）。这两类事件被收进 `toolCards` 状态，
`App.jsx` 据此拼出一个 `{steps:[...]}` 形状的 trace 对象传给右侧
`TracePanel`（和非流式 `/api/chat` 的 `trace` 复用同一个组件/同一套
`trace-step` 展现逻辑），每个工具调用显示为一个可展开的 step，状态为
`running`/`ok`/`error`。

后端启动：

```bash
# Configure LLM_BASE_URL, LLM_MODEL, and LLM_API_KEY in the environment.
.venv-py314/bin/python -m chat_service.run
```

前端启动：

```bash
cd chat_service/frontend
npm install
npm run dev
```

## 当前边界

taxonomy 仍由 `kb_classifier` 提供，chat_service 不修改 taxonomy 版本、阈值或匹配
算法。文档导入已接入 embedding 和 ChromaDB；`/api/chat` 使用短期 Checkpointer，
不执行 RAG。RAG 仍由独立的 `/api/ask` 提供。

流式端点依赖 langchain-core 1.x / langgraph 1.x（`get_stream_writer` 与
`stream_mode="updates"` 需要 1.x）。仓库运行时已升级到 Python 3.14，
依赖装在 `.venv-py314`。
