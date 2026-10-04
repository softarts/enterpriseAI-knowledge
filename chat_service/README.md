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

### 前端 SSE 消费流程

前端在 `chat_service/frontend/src/api/chatApi.js:61-89` 的 `consumeSSE()` 函数中读取 SSE 流：

```javascript
// chatApi.js:61-89
async function consumeSSE(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Frames separated by "\n\n", parse each JSON payload
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const payload = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (!payload) continue;
      try {
        onEvent(JSON.parse(payload));  // 传给 onEvent 回调
      } catch { /* ignore malformed frames */ }
    }
  }
}
```

流程：
1. **读取字节**：`response.body.getReader()` 逐块读取响应体
2. **SSE 帧解析**：按 `\n\n` 分界符分割帧，提取 `data:` 行后的 JSON
3. **事件回调**：每收到一个完整事件就调用 `onEvent(parsedEvent)` 回调

**回调入口**：
- `App.jsx:129` 中的 `handleSend()` 调用 `askQuestionStream(question, { onEvent: handleStreamEvent })`
- 回调函数是 `App.jsx:45-108` 的 `handleStreamEvent(event)`，它根据 `event.type` 分发处理：
  - `"token"` → 追加到当前消息气泡文本（`appendToStreaming`）
  - `"trace"` → 添加 trace 条目（llm/tool/http/local）到 timeline，按 `seq` 覆盖
  - `"interrupt"` → 弹出 HITL 确认对话框
  - `"done"` → 清除加载状态
  - `"error"` → 显示错误消息

后端和前端共用一套 SSE 协议，事件类型在 `stream_events.py` 中定义，前端按类型分流处理。

### 事件协议

每帧是一个 JSON 对象，`type` 决定前端分流：

```jsonc
{"type":"token","text":"你好","turn":1}
{"type":"node_start","node":"agent"}
{"type":"trace","seq":0,"kind":"llm","name":"llm_call","status":"pending","detail":{"request":{"messages":[...],"tools_bound":[...],"node":"agent"}},"duration_ms":null,"conversation_id":"conversation-...","llm_call_id":"01a1..."}
{"type":"trace","seq":1,"kind":"http","name":"llm_request","status":"pending","detail":{"method":"POST","url":"https://.../chat/completions","attempt":1,"headers":{...},"body":"{...}"},"duration_ms":null,"llm_call_id":"01a1..."}
{"type":"trace","seq":1,"kind":"http","name":"llm_response","status":"ok","detail":{"method":"POST","url":"https://.../chat/completions","attempt":1,"status_code":200},"duration_ms":378.1,"llm_call_id":"01a1..."}
{"type":"trace","seq":2,"kind":"tool","name":"web_search","status":"running","detail":{"arguments":{"query":"news"}},"duration_ms":null,"tool_call_id":"call_1"}
// 同 seq 的 llm/tool 行会再发一次，status 从 pending/running 变成 ok/error，
// detail 里补上聚合响应/工具结果和耗时；客户端应按 seq 覆盖同一行。
{"type":"trace","seq":0,"kind":"llm","name":"llm_call","status":"ok","detail":{"request":{...},"response":{"role":"assistant","content":"...","tool_calls":[{"name":"web_search","args":{...}}],"usage":{...}}},"duration_ms":812.4,"llm_call_id":"01a1..."}
{"type":"trace","seq":2,"kind":"tool","name":"web_search","status":"ok","detail":{"arguments":{"query":"news"},"result":"Web search results..."},"duration_ms":1204.7,"tool_call_id":"call_1"}
{"type":"interrupt","thread_id":"conv-1","question":"即将调用外部工具 web_search，是否继续？","resume_key":"conv-1:call_1","tools":[...]}
{"type":"done","usage":{"input_tokens":812,"output_tokens":96},"finish_reason":"stop"}
{"type":"error","message":"...","code":"upstream"}
```

> **没有 `tool_call` / `tool_result` 事件了。** 两者都已删除，因为它们和
> `trace` 行是同一份信息：模型"决定"调用工具 =
> `llm_call` → `detail.response.tool_calls`（id/name/args 完全一致，直接读自
> 聚合后的消息）；工具"真的执行" = `tool` 行（arguments/result/status/duration，
> 按 `tool_call_id` 关联）。两者都发会让一次搜索显示成两行，读起来像"执行了两次"。

`finish_reason` 为 `interrupt` 表示本轮因 HITL 暂停（此时 `usage` 为 null）；
流在 `done` 事件后结束，前端可无条件清除 loading 状态。

### 后端 stream event 生产流程（最小例子）

在 `chat_service/services/chat/chat_stream.py` 中，`ChatStreamService._run()` 是核心驱动：

```python
# chat_stream.py:206-231（简化版，省略 finally 块）
with call_trace.trace_scope() as call_entries:
    async for mode, chunk in graph.astream(
        inputs,
        config=config,
        stream_mode=["custom", "messages", "updates"],  # 三路 stream mode
    ):
        if mode == "custom":
            events = mapper.map_custom(chunk)         # LLM token / tool_call
        elif mode == "messages":
            events = mapper.map_messages(chunk)       # node_start / AIMessage
        elif mode == "updates":
            events = mapper.map_updates(chunk)        # tool_result / interrupt
            final_state = _absorb_updates(chunk, final_state, tool_messages)
        else:
            events = []
        
        # 插入本轮新增的 trace 条目（llm/tool/http/local），以及已被
        # 原地 finalize 的旧条目（同 seq 覆盖）
        for trace_event in drain.drain():
            yield trace_event
        
        # 产生本 chunk 对应的事件
        for event in events:
            if event.type == "interrupt":
                interrupted = True
            yield event  # 发送到前端
```

**关键点**：
- Line 208：`graph.astream(stream_mode=["custom","messages","updates"])` 触发图的异步流式执行
- `async for mode, chunk in ...` 是 Python async 迭代，每收到一个 chunk（来自 LangGraph 的某个 stream mode），循环体就执行一次
- `yield event` 把事件送出去，这是异步生成器（async generator）—— 每一次 `yield` 会**暂停**当前协程，释放 CPU 给事件循环处理其他任务（如网络 I/O、其他并发请求）
- 框架（FastAPI + Starlette）负责把这些 `yield` 出来的事件转成 SSE 帧（通过 `event.to_sse()` 方法，见下面的路由层）

后端的流程是：**LangGraph astream 驱动图执行 → 每 chunk 调一次 mapper 转事件 → 每个事件 yield 给前端（释放 CPU） → 流式接收端（前端）逐个处理**。

#### 三路 stream mode 的分工

LangGraph 的 token 有两条限制，因此需要同时消费三个通道：

| 通道 | 提供 | 说明 |
|---|---|---|
| `custom` | token、tool_call | 节点内 LLM 的 chunk **不会**冒泡为 `on_chat_model_stream`，只能由 agent 节点用 `get_stream_writer()` 主动写出 |
| `messages` | node_start | `(message, metadata)` 元组，`metadata["langgraph_node"]` 是节点名 |
| `updates` | interrupt | 节点级 state delta；暂停运行时顶层出现 `__interrupt__` 键 |

工具的**执行**（arguments/result/status/duration）不走流式载荷，而是由
`call_trace` 的 `on_tool_start`/`on_tool_end` 回调记录成 `kind:"tool"` 的 trace
行——这是唯一能看到 `web_search` 的层（它走 `requests`/`aiohttp`，httpx 钩子对
它不触发）。`usage` 取自 `updates` 通道最终 AIMessage 的 `usage_metadata`。

`token_scope`：`all`（默认）立即转发每轮 token；`final` 先缓冲，只有在没发生工具
调用时才在结束时输出，避免把"决定调工具"那轮的中间文本暴露给用户。

#### 路由层转 SSE（chat_service/api/routes_chat.py:120-135）

```python
async def event_stream():
    task = asyncio.current_task()
    if task is not None:
        _ACTIVE_STREAMS[conversation_id] = task
    try:
        async for event in _chat_stream_service.stream_turn(...):
            if await raw_request.is_disconnected():
                logger.info("chat.stream.client_disconnected id=%s", conversation_id)
                break
            yield event.to_sse()  # StreamEvent -> "data: {...}\n\n"
```

每个 `event` 都被转成 SSE 文本帧 `"data: {json}\n\n"`，由 `StreamingResponse` 推送给客户端。



### LLM / 工具 / HTTP / 本地函数 trace

Trace 面板现在能看到四类条目，明确区分开（`kind` 字段）：

- `kind: "llm"` —— **一次 LLM 调用一条**，带这次调用的 request 和**聚合后**
  的 response。由 `call_trace.LlmTraceHandler` 从 LangChain 自己的
  `on_chat_model_start` / `on_llm_end` 回调里取，所以无论 provider 在 wire
  上是不是流式返回、返回多少个 chunk，这次调用只产生一条记录，内容就是这轮
  对话该次调用的完整 payload（含 `tool_calls`、`usage_metadata`、
  `finish_reason`）。request 里还带 `tools_bound`（本轮绑定了哪些工具）、
  `node`（由哪个图节点发起）、`stream`（是否走 SSE）。
- `kind: "tool"` —— 一次**工具执行**一条，来自 `on_tool_start` /
  `on_tool_end`，带 `arguments` / `result` / 耗时。这是唯一能看到
  `web_search` 的层：它走 `langchain_tavily`，底层是 `requests`/`aiohttp`，
  不是 httpx，所以下面 `kind: "http"` 的钩子对它完全不触发——之前搜索请求对
  trace 是隐形的。
- `kind: "http"` —— 发往/收到 **云端 LLM API** 的真实 HTTP request/response，
  每次实际尝试各一条，带 `method`/`url`/`status_code`/`attempt`；OpenAI SDK
  内部触发的**重试**会产生新的一对 `attempt` 更高的条目，不需要额外的重试
  跟踪逻辑——这就是 httpx 的 `event_hooks` 天然给的。request 条目现在**会记录
  出站 body**（httpx 把它存为可重放的 `ByteStream`，在 hook 里读不会消费掉
  LangChain 需要的东西），所以这里能看到**真实** wire payload，包括
  langchain-openai 内部补上的 `stream`/`stream_options`——本地重建的请求体
  预览是看不到这些的。仍然**不读取 response body**：chat-completion 调用走 SSE
  流式返回，在 hook 里读会把流"偷走"，让 LangChain 自己的消费者拿不到内容；
  聚合后的回答改由上面的 `kind: "llm"` 记录。
- `kind: "local"` —— 图里各节点的函数级 span（`hitl_gate`、
  `search_budget_check`、`force_finalize`），带耗时和与该节点决策相关的小
  detail（例如 `search_budget_check` 带上 `search_count`/`limit`/`exhausted`）。

`agent` 节点**不再**自己记录 span：以前它在节点里手搓 `"".join(parts)` 聚合
chunk 再 `record_local("agent", ...)`，那等于把 langchain-core 已经做过的
合并重做一遍（而且重做出来的 request body 预览缺少 `stream` 等内部字段）。
现在改由回调提供聚合结果，`agent`/`force_finalize`/`update_memory` 的归属
信息保留在 `kind: "llm"` 条目的 `detail.request.node` 里。

### `llm` 和 `http` 两条的关系：不是重复，是两层

一次 LLM 调用会产生**三条** trace（一次 `llm` + 一对 `http`），它们回答的是
不同问题，靠 `llm_call_id` 串起来：

| 条目 | 谁记的 | 回答什么 | 有没有 payload |
|---|---|---|---|
| `llm_call` | `on_chat_model_start` / `on_llm_end` | **模型说了什么**：合并后的回答、`tool_calls`、`usage`、`finish_reason` | 有（聚合后的语义） |
| `llm_request` | httpx `request` hook | **实际发出去什么**：method/url/headers/**原始 body** | 有（wire 上的原文 JSON） |
| `llm_response` | httpx `response` hook | **网络层发生了什么**：attempt、status_code、耗时 | 没有 body（见下） |

`llm_request.body` 和 `llm_call` 的 request **不是同一份东西**，各有不可替代的
信息：

- `llm_call` 的 request 是 LangChain **侧**重建的摘要（消息列表 + 工具名 +
  `stream` 开关），可读性好，但没有 `stream_options`、没有真实的 tool schema JSON。
- `llm_request.body` 是 httpx 上**真正的字节**，因此含 langchain-openai 内部
  补上的字段（`stream`、`stream_options`）和逐字的 tool 定义。想复现"模型为什么
  不调工具"，只能看这条。

`llm_response` 没有 body 是**刻意的**：chat-completion 走 SSE 流式返回，在
response hook 里读 body 会把流偷走，让 LangChain 自己的消费者拿不到内容。聚合后
的回答由 `llm_call` 那条提供，所以信息并没有丢。

`llm_call_id` 的串联方式：`on_chat_model_start` 把当前最内层 run_id 写进
ContextVar → httpx `request` hook 读到后盖到 request 的 extensions →
`response` hook 再读回来。所以同一次调用的三条 trace 带同一个 `llm_call_id`
（OpenAI SDK 内部重试会产生 attempt 更高的一对，同样归到同一个 id 下）。

实现见 `langchain_agent/app/call_trace.py`：一个 `contextvars.ContextVar`
按"一轮对话"作用域收集条目（`trace_scope()`），`LlmTraceHandler`（通过
`build_trace_callbacks()` 挂到 `graph.astream/invoke` 的 `config["callbacks"]`）
负责 `llm`/`tool` 两类，`record_local(...)` 供图节点记录决策类 span，
`build_traced_http_clients()` 返回挂了 `event_hooks` 的
`httpx.Client`/`httpx.AsyncClient`，传给 `langchain_agent/app/config.py` 的
`get_chat_model()` 和 `qa_service/llm_client.py` 的 `_build_llm()`（这两处是
聊天图实际用到的两个 `ChatOpenAI` 构造点）。`Authorization`/`api-key` 请求头
在落入 trace 前就地替换成 `"***"`，不会有密钥泄漏到前端或日志。

两个入口的接入方式不同：

- 非流式 `/api/chat`：`ChatService.ask()` 用 `call_trace.trace_scope()` 包住
  `generate_answer_with_memory(...)` 整次调用，结束后把收集到的条目逐一
  `trace.add_step(kind=..., ...)` 插入 `TraceBuilder`，和原有的 `request`/
  `llm`/`response` 步骤按时间顺序混在同一个 `steps` 列表里。
- 流式 `/api/chat/stream`：**不是**等到整轮跑完才一次性抽干。
  `call_entries` 是 `call_trace.trace_scope()` 返回的同一个列表，图节点跑的
  时候（回调/`record_local`/httpx hook）会原地往里 append；`ChatStreamService._run`
  在 `graph.astream(...)` 的主循环里，每收到外层的一个 chunk 就先
  `drain.drain()` 一次，再发这个 chunk 自己的事件，循环结束后再抽干一次收尾。
  这保证了真实的时间顺序：一轮 `agent` 节点里，HTTP 请求/响应发生在
  `llm_with_tools.astream()` 真正开始流式返回内容之前，所以 `llm_request`/
  `llm_response` 两条会先于该轮 `llm_call` 的 finalize 出现——而不是像最初实现那样，
  所有 trace 条目都在最后一次性堆在节点事件后面，顺序和
  实际发生顺序对不上。

`llm`/`tool` 条目是**先 provisional 后 finalize**的：`on_chat_model_start` 时先
追加一条 `status="pending"` 的条目（这样它在时间线上的位置就是这次调用真正的
位置），`on_llm_end` 再**原地**补上聚合响应和耗时。为了让流式 UI 能感知这种
"就地更新"，`chat_stream.py` 的 `_TraceDrain` 会把已抽干但状态发生变化的条目
**再发一次**（`seq` 不变），前端按 `seq` 覆盖同一行而不是追加。`trace` 事件因此
带一个稳定的 `seq` 字段（该条目在本轮 sink 里的下标）。

#### 一次 web_search 回合的真实顺序（别被行数骗了）

问题 `pura x view 用的是什么芯片` 的实际事件顺序（实测）：

```
 1. llm      llm_call   (pending)  ← 模型这次调用开始了
 2. node_start agent
 3. llm      llm_call   (ok)        ← 同一次调用 finalize，response.tool_calls 里有 web_search ←「决定搜索」
 4. local    hitl_gate              ← HITL 闸门（web_search 默认自动放行，不 interrupt）
 5. local    search_budget_check    ← 预算检查：还没超，继续走 tools
 6. node_start tools
 7. tool     web_search (ok)        ← 工具"真的执行"了 ←「执行搜索」
 8. node_start agent
 9. llm      llm_call   (pending)   ← 带着 ToolMessage 再问模型一次
10. token    ...
11. llm      llm_call   (ok)
12. node_start update_memory
13. done
```

关键点，也是最容易被误读的地方：

- **一次搜索只有一条 `tool` 行。** 「决定调用」（第 3 行，模型返回的
  `tool_calls`）和「执行」（第 7 行，`on_tool_end`）是两个不同事实，分别记在
  `llm_call` 行和 `tool` 行上。以前还会额外发 `tool_call`/`tool_result` 事件，
  两者和 trace 行信息完全重复，于是界面上出现两条 web_search——看起来像搜索了
  两次。**已删除**。界面上展开 `llm_call` 会看到
  `↳ This call requested a tool`，说明下面的 `tool` 行是执行而非第二次调用。
- **`llm_request` 里确实有 tools schema。** 实测 `_get_request_payload` 产出的
  顶层键是 `['messages','model','stream','tools']`，`tools` 里是完整的 function
  定义。之前"看不到"是因为 UI 没渲染——现在 `llm_request` 行有
  **Request Body** 段落（标注 *as sent on the wire*），可展开/收起。
- **`hitl_gate` / `search_budget_check` 不是"又一次搜索"。** 它们是图节点做的
  两个纯决策 span，夹在"决定调用"和"执行"之间：闸门放行、预算够用，于是
  路由到 `tools`。

**还有第四种截断**：`tool` 行里的 result 是**模型实际看到的那份文本**。`web_search`
在 `tool_layer.py` 里用 `MAX_WEB_SEARCH_CHARS = 2000` 截断后才交给模型——这是
**模型输入预算**，不是 trace 预算。trace 忠实地记录模型收到的东西（排查"为什么
答得不对"时该看的正是这个数）。界面在检测到 `...[truncated]` 时会明确提示，
以免看起来像 trace 把它截了。

**如果 `TAVILY_API_KEY` 没配**，`web_search` 会返回
`Tool failed: TAVILY_API_KEY is not configured`，在 `tool` 行里一眼可见。

#### 两条不能踩的坑

**① `trace` 的标识字段必须是字符串。** LangChain 传给回调的 `run_id` 是
`uuid.UUID` **对象**（不是 str）。它会经 `llm_call_id`/`tool_call_id` 进入 SSE
帧，`json.dumps` 遇到 UUID 会抛
`TypeError: Object of type UUID is not JSON serializable`。而这个异常发生在
Starlette 的 **ASGI send 路径**里——不是"某一帧丢了"，而是整个响应被中断，
且此时 `trace_scope` 的 `ContextVar` 清理又会在另一个 task 里触发第二个异常，
最终变成两段互不相干的 traceback，真正的首因被埋掉。因此：
`LlmTraceHandler` 在入口一律 `str(run_id)`；`StreamEvent.to_sse()` 另外带
`default=str` 兜底——**纯诊断字段永远不该弄死一个响应**。

**② `ContextVar.reset()` 只能在创建它的 Context 里调用。** SSE 的 body
iterator 是一个跨 `yield` 挂起的生成器；客户端断开（或某帧序列化失败）时，
Starlette 的 task group 会在**另一个 task** 里 finalize 它，于是 `trace_scope`
的 `finally` 在另一个 Context 执行，`reset()` 抛
`ValueError: ... was created in a different Context`。丢掉这次 reset 是无害的
（设置它的那个 Context 本来就要被丢弃），所以 `trace_scope` 捕获并降级。

> 这两条都有回归测试：
> `test_sse_frame_survives_non_serializable_values`、
> `test_identifiers_are_strings_so_frames_stay_serializable`、
> `test_abandoned_stream_does_not_raise_on_scope_teardown`。
> 注意最后一条必须跑在**活着的 loop** 上并从另一个 task 关闭生成器——用
> `asyncio.run` 时，loop 关停会就地 cancel 掉挂起的生成器，不会跨 Context，
> 于是**带着 bug 也能通过**。

前端：`App.jsx` 的 `timeline` 状态把 `trace` 事件按到达顺序合并成一条时间线，
交给 `TracePanel`；`trace` 事件按 `seq` 覆盖（provisional → finalized）。
`StepRow` 的 `KindPill` 现在渲染
`LLM`/`TOOL`/`HTTP`/`LOCAL` 四种小胶囊（此前 `kind:"tool"` 被显式隐藏，且
CSS 里根本没有 `--tool`/`--llm` 配色）；`kind:"llm"` 用专门的
`LlmCallStepDetail` 渲染 node/tools_bound/request/聚合响应/tool_calls，
`kind:"http"` 用 `HttpStepDetail`，其余走通用的 `JSON.stringify` 兜底。

#### 写入日志文件（`logs/chat_service.log`）

`chat_service/run.py` 现在同时往 console 和 `logs/chat_service.log`（仓库根目录
下，`RotatingFileHandler`，20MB × 5 份）写日志；`logs/` 已加进 `.gitignore`。
每条 `call_trace` 条目（四种 kind 都算）在被塞进 trace sink 的同一
时刻，也会以 `call_trace.entry [conversation-xxxx] {json}` 的格式打一条 INFO
日志——所以即使这次
请求最终没有通过 UI 看到（例如客户端提前断开、或者只是单纯想离线分析一次失败
请求），仍然能直接从日志文件里用 `grep` 还原出完整的 LLM/工具/HTTP/本地函数
时间线，不需要复现一遍。`llm`/`tool` 条目在 finalize 时会**再打一次**，
所以日志里能看到同一 `llm_call_id` 的 pending 行和 ok 行（后者带聚合响应）。
`force_finalize` 泄漏检测命中时的 WARNING 日志（见上一节）也
会落进同一个文件。

任何记录失败都不会影响真实请求——`record_local`/`record_tool`/回调处理
内部全部 `try/except`，纯诊断用途。

**payload 不截断。** 请求体、聚合回答、工具结果都**全文保留**：trace 是排查
工具，一个被悄悄截短的 payload 比一个长 payload 更糟——你无法区分"被截断"
和"本来就这么短"。只有异常文本按 `MAX_ERROR_CHARS`（500）截断，因为
`str(exc)` 可能任意长且没有额外信息量。前端负责可读性：`RawOutput` 在超过
600 字符时默认折叠，显示 `展开全部 / 收起` 和总字符数，Copy 永远复制全文。

#### 每条 trace 都带 conversation id

多轮对话会在同一个日志文件、同一条 UI 时间线里交错，所以每条 trace entry
都带 `conversation_id`（由 `trace_scope(conversation_id=...)` 盖上，见
`chat_service.py` 与 `chat_stream.py` 的调用点）：

- **日志**：`call_trace.entry [conversation-ae17acaa] {json}` —— 前缀是
  conversation id 的可读头（`conversation-<uuid>` 取前 8 位），可以直接
  `grep conversation-ae17`，不必解析 JSON；完整 id 也在 JSON 里。
- **SSE `trace` 事件**：带 `conversation_id` 字段。
- **前端**：聊天窗口顶部显示当前 conversation id（`title` 属性是完整值）并
  提供 **New** 按钮开新对话（后端按 id 隔离短期记忆，所以新 id = 下一问干净
  开始）；Trace 面板标题和每一行也都显示这个 id（截断显示，`title` 保留全文），
  这样从日志里粘出来的 trace 仍然可归属。
- **New 是归档不是丢弃**：点 New 时当前 trace 会被快照进 `archivedTraces`
  （最多 `MAX_ARCHIVED_TRACES = 5` 条），在面板下方**折叠**保留，随时展开查看。
  上一轮 trace 通常正是你开新对话的原因，不该被抹掉。聊天消息本身也保留，
  只有"下一问从哪开始"的记忆上下文被重置。

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

工具调用（`llm_call` 的 `tool_calls` 和 `tool` 行）**不**渲染在聊天窗口里
——聊天窗口只显示最终回答（以及 error 消息和 HITL 确认框）。这些行被收进
`timeline` 状态，`App.jsx` 据此拼出一个 `{steps:[...]}` 形状的 trace 对象传给右侧
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

## ChatService 与非流式 `/api/chat` 是否废弃

**否**。`ChatService.ask()` 仍然在使用：

- 路由：`chat_service/api/routes_chat.py:58-79` 的 `@router.post("/api/chat")` 
- 实现：`chat_service/services/chat/chat_service.py:34-165` 的 `ChatService.ask()`
- 用途：非流式单次问答，返回 `{answer, trace, error}` JSON 对象

非流式与流式的选择：
- 非流式 `/api/chat` — 适合单纯的问答，收完答案再一次性返回；同步 Python 实现
- 流式 `/api/chat/stream` — 适合实时 token 展示、长回答、工具调用过程可见；异步 Python + SSE

前端主聊天界面（`App.jsx`）目前**只使用** `/api/chat/stream`（见 `App.jsx:129`），
但 `ChatService` 仍是备选方案，也许被其他客户端或非浏览器场景使用。两个实现都走同一套
Checkpointer、LangGraph 图和 LLM 客户端，只是一个等答案做完再返，一个边跑边推流。

## 当前边界

taxonomy 仍由 `kb_classifier` 提供，chat_service 不修改 taxonomy 版本、阈值或匹配
算法。文档导入已接入 embedding 和 ChromaDB；`/api/chat` 和 `/api/chat/stream` 都使用短期 Checkpointer，
不执行 RAG。RAG 仍由独立的 `/api/ask` 提供。

流式端点依赖 langchain-core 1.x / langgraph 1.x（`get_stream_writer` 与
`stream_mode="updates"` 需要 1.x）。仓库运行时已升级到 Python 3.14，
依赖装在 `.venv-py314`。
