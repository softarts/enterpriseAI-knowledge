# MCP Server 设计文档

## 1. MCP 与 REST API 的整体架构

MCP Server 是 doc_service 的一个接口层，与 FastAPI REST API 平行存在，共享同一套 Service / Repository / 数据访问逻辑。

```
doc_service
├── FastAPI REST API (:8000)
│   ├── GET /documents
│   ├── GET /documents/{document_id}
│   └── GET /search
│
└── MCP Server (:8001)
    ├── list_documents
    ├── query_documents
    └── get_document
```

两个接口共享同一个 KnowledgeService 实例：

```
Kiro Agent                          普通客户端
    │                                    │
    │ MCP over HTTP                      │ REST API
    ▼                                    ▼
doc_service :8001                   doc_service :8000
    │                                    │
    └──────────────┬─────────────────────┘
                   ▼
           Knowledge Service
                   │
                   ▼
           OKF Repository
                   │
                   ▼
         ./generated/*.yaml
```

## 2. 两个 HTTP endpoint / port

| 接口 | 端口 | 协议 | 用途 |
|---|---|---|---|
| REST API | 8000 (KB_PORT) | HTTP/JSON | 普通客户端访问 |
| MCP Server | 8001 (KB_MCP_PORT) | MCP Streamable HTTP | Kiro Agent 访问 |

端口通过环境变量配置，不硬编码：
- `KB_PORT` → REST API 端口（默认 8000）
- `KB_MCP_PORT` → MCP Server 端口（默认 8001）
- `KB_HOST` → 绑定地址（默认 0.0.0.0，两者共用）

## 3. MCP 与 Knowledge Service / Repository 的关系

MCP tools 直接调用 `KnowledgeService` 的方法，不经过 HTTP：

```
MCP Tool: list_documents
    → KnowledgeService.list_documents()
        → OKFDocumentRepository.list_documents()

MCP Tool: query_documents
    → KnowledgeService.search()
        → KeywordRetriever.retrieve()

MCP Tool: get_document
    → KnowledgeService.get_document()
        → OKFDocumentRepository.get_document()
```

MCP 层不重复实现文档读取、搜索或 Repository 逻辑。

## 4. 三个 MCP Tools

### 4.1 list_documents

列出知识库文档。

**参数：**
- `keyword` (Optional[str]) — 标题关键词过滤
- `tag` (Optional[str]) — 标签过滤

**返回：** JSON 文档列表

```json
[
  {
    "document_id": "...",
    "title": "...",
    "author": "...",
    "created_at": "...",
    "tags": ["finance", "legal"],
    "source_path": "..."
  }
]
```

### 4.2 query_documents

根据 query 查询知识库，返回相关 chunk。

**参数：**
- `query` (str) — 搜索关键词
- `top_k` (Optional[int], 默认 5) — 返回数量

**返回：** JSON 搜索结果列表

```json
[
  {
    "chunk_id": "...",
    "document_id": "...",
    "title": "...",
    "heading": "...",
    "content": "...",
    "score": 0.85,
    "source_path": "..."
  }
]
```

### 4.3 get_document

根据 document_id 获取完整文档。

**参数：**
- `document_id` (str) — 文档 ID

**返回：** JSON 文档对象

```json
{
  "document_id": "...",
  "title": "...",
  "author": "...",
  "created_at": "...",
  "tags": ["finance", "legal"],
  "source_path": "...",
  "content": "..."
}
```

## 5. MCP HTTP Transport

- 使用 MCP Python SDK v2 (`mcp>=2.0.0`)
- Transport: Streamable HTTP
- Endpoint: `http://localhost:8001/mcp`
- 不使用 stdio，不使用已废弃的 SSE transport

## 6. 启动和部署方式

### 统一启动（推荐）

```bash
python -m doc_service.mcp_main
```

同时启动 REST API (:8000) 和 MCP Server (:8001)，共享同一进程和 KnowledgeService 实例。

### 单独启动 REST API（向后兼容）

```bash
uvicorn doc_service.main:app --port 8000
```

### 环境变量

```bash
KB_OKF_DIR=./generated    # OKF 文档目录
KB_HOST=0.0.0.0           # 绑定地址
KB_PORT=8000              # REST API 端口
KB_MCP_PORT=8001          # MCP Server 端口
```

## 7. Kiro 如何连接 MCP

在 `.kiro/settings/mcp.json` 中配置：

```json
{
  "mcpServers": {
    "enterprise-kb": {
      "url": "http://localhost:8001/mcp",
      "disabled": false
    }
  }
}
```

Kiro Agent 启动后自动连接该 MCP Server，可通过 MCP 调用 list_documents、query_documents、get_document。

## 8. POC 验收标准

- [ ] `python -m doc_service.mcp_main` 启动后，REST API (:8000) 和 MCP (:8001) 同时可用
- [ ] 现有 REST API 行为不变（GET /documents, GET /documents/{id}, GET /search）
- [ ] MCP Server 可被 Kiro Agent 发现并列出 3 个 tools
- [ ] `list_documents` 返回知识库文档列表
- [ ] `query_documents` 返回搜索结果
- [ ] `get_document` 返回完整文档内容
- [ ] MCP 与 REST API 共享同一个 KnowledgeService/Repository（数据一致）

## 9. 项目文件变更

| 文件 | 操作 | 说明 |
|---|---|---|
| `doc_service/core/config.py` | 修改 | 增加 MCP 端口配置 |
| `doc_service/mcp/__init__.py` | 新增 | MCP 模块 |
| `doc_service/mcp/server.py` | 新增 | MCP Server + 3 Tools |
| `doc_service/mcp_main.py` | 新增 | 统一启动脚本 |
| `requirements.txt` | 修改 | 增加 mcp 依赖 |
| `.kiro/settings/mcp.json` | 新增 | Kiro 连接配置 |
| `tests/test_mcp_tools.py` | 新增 | MCP Tools 测试 |

## 10. 依赖

```
mcp>=2.0.0
```

MCP SDK 自带 Starlette、uvicorn 等依赖，无需额外安装 ASGI 相关包。
