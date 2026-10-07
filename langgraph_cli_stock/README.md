# LangGraph CLI Stock Assistant

A command-line chat application using LangGraph with OpenAI-compatible API and stock price查询功能。

## Python 版本要求

- Python 3.11+
- 当前项目使用 Python 3.14 开发

## 安装依赖

```bash
cd langgraph_cli_stock
pip install -r requirements.txt
```

## 环境变量配置

创建 `.env` 文件并配置以下环境变量：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

- `LLM_API_KEY`: 你的 LLM API 密钥
- `LLM_BASE_URL`: OpenAI-compatible API 端点
- `LLM_MODEL`: 使用的模型名称

## 启动应用

### 默认启动（使用 user_id 1234）

```bash
python -m app
```

### 指定 user_id

```bash
python -m app --user-id 1001
```

## CLI 内置命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助信息 |
| `/history` | 显示对话历史 |
| `/clear` | 清除对话历史 |
| `/exit` | 退出应用 |
| `/quit` | 退出应用 |

## 启动信息

应用启动时会显示：
- 当前 user ID
- 当前 LLM model
- 已注册的工具名称
- 日志目录位置

## 查看 JSONL 日志

日志文件位于 `logs/` 目录下，按运行实例生成 JSONL 文件。

### 日志字段说明

每条日志记录包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | string | ISO 格式时间戳 |
| `trace_id` | string | 唯一追踪 ID，贯穿整轮调用链 |
| `event_type` | string | 事件类型（user_input, llm_http_request, tool_call 等） |
| `component` | string | 组件名称（cli, graph, llm_client 等） |
| `sequence` | integer | 同 trace 内的序号，保证顺序 |
| `payload` | object | 事件具体数据 |

### 常用 event_type

- `user_input`: 用户输入
- `llm_http_request`: LLM HTTP 请求
- `llm_http_response`: LLM HTTP 响应
- `graph_node`: LangGraph 节点执行
- `tool_call`: 工具调用
- `tool_execution`: 工具执行
- `memory_operation`: 内存操作
- `final_response`: 最终响应
- `error`: 错误

### 通过 trace_id 还原调用链

每轮用户输入生成一个唯一的 `trace_id`，该 ID 贯穿整轮调用链。使用以下命令聚合查看：

```bash
# 查看特定 trace 的所有日志
grep "trace-xxx-xxx" logs/trace_*.jsonl

# 使用 jq 格式化输出
grep "trace-xxx-xxx" logs/trace_*.jsonl | jq '.event_type, .component, .payload'
```

### LLM Payload 脱敏

日志中对敏感信息进行脱敏处理：

- `Authorization` header 中的 API Key 被替换为 `<AUTHORIZATION_REDACTED>`
- JSON payload 中的 `api_key` 字段被替换为 `<API_KEY_REDACTED>`
- Cookie 等敏感 header 被脱敏

**重要**：日志中绝不会出现真实的 `LLM_API_KEY`。

## yfinance 限制和适用范围

- 数据源：使用 Yahoo Finance (yfinance)
- 适用：美股历史价格查询
- 限制：
  - 只能查询已上市股票
  - 历史数据可能有延迟
  - 某些股票可能无数据
  - 不提供实时数据

## 示例对话

### 普通问题

```
User: Hello, how are you?
Assistant: Hello! I'm doing well, thank you for asking. How can I help you today?
```

### 股票价格查询

```
User: What was Apple's stock price on 2024-01-15?
```

**调用链**：
1. 用户输入 -> CLI (`cli.py`, `run()` 方法)
2. 生成 trace_id
3. 进入 LangGraph -> `model_node` (`graph.py`, `model_node()` 函数)
4. LLM 分析意图，决定调用 `stock_price` 工具
5. 记录 `llm_http_request` 和 `llm_http_response`
6. `should_continue` 返回 "tools" -> 进入 `tool_node` (`graph.py`, `tool_node()` 函数)
7. 执行 `stock_price` 工具 (`tools/__init__.py`, `stock_price()` 函数)
8. 工具调用 yfinance 获取数据
9. 工具结果返回给 graph
10. 再次进入 `model_node`，将工具结果发送给 LLM
11. LLM 生成最终回答
12. 记录 `final_response`
13. 输出给用户

### 函数流程图

```
User Input
    |
    v
[CLI.run()] --> 生成 trace_id
    |
    v
[run_agent()] --> 调用 LangGraph
    |
    v
[model_node] --> 调用 LLM
    |                    |
    |                    v
    |              [llm_client.chat()]
    |                    |
    |                    v
    |              HTTP Request/Response
    |                    |
    v                    v
should_continue? ----[LLM Response]
    |                    |
    | yes                | no tool calls
    v                    v
[tool_node]         final_answer
    |
    v
execute_tool() --> stock_price()
    |
    v
yfinance API
    |
    v
返回结果给 LLM
    |
    v
[model_node] 再次调用
    |
    v
final_answer --> 输出
```

## Call Trace 实现

### 使用的库

- **httpx**: HTTP 客户端，用于 LLM API 调用
- **logging**: Python 内置日志模块
- **langgraph**: LangGraph 状态图框架

### Hook 位置

1. **LLM HTTP 请求/响应拦截**：
   - 在 `llm_client.py` 中封装了 `httpx.Client`
   - 在 `_log_request()` 和 `_log_response()` 方法中记录完整的 HTTP payload
   - 使用 `redact_headers()` 和 `redact_json_payload()` 脱敏敏感信息

2. **LangGraph 节点执行**：
   - `graph.py` 中各节点函数（`model_node`, `tool_node`）记录执行日志

3. **工具调用**：
   - `tools/__init__.py` 中 `stock_price()` 函数记录工具调用和结果

4. **Memory 操作**：
   - `memory.py` 中 `log_memory_operation()` 记录内存读写

## 项目结构

```
langgraph_cli_stock/
├── README.md              # 本文件
├── requirements.txt       # Python 依赖
├── .env.example          # 环境变量示例
├── logs/                  # 日志目录
├── app/
│   ├── __init__.py
│   ├── __main__.py       # 模块入口
│   ├── cli.py            # CLI 应用
│   ├── config.py         # 配置管理
│   ├── graph.py          # LangGraph 定义
│   ├── state.py          # Agent 状态定义
│   ├── memory.py         # 记忆管理
│   ├── llm_client.py     # LLM 客户端（含日志）
│   ├── logging_config.py # 日志配置
│   ├── trace.py          # Trace ID 生成
│   ├── tools/
│   │   ├── __init__.py   # 工具注册
│   │   └── stock.py      # 股票数据源
│   └── utils/
│       ├── __init__.py
│       └── redaction.py  # 敏感信息脱敏
└── tests/
    ├── test_config.py
    ├── test_trace_logging.py
    ├── test_stock_tool.py
    └── test_graph.py
```

## 测试

运行测试：

```bash
cd langgraph_cli_stock
python -m unittest discover -s tests -t .
```

或运行单个测试文件：

```bash
python -m unittest tests.test_config
python -m unittest tests.test_trace_logging
python -m unittest tests.test_stock_tool
python -m unittest tests.test_graph
```

## 扩展开发

### 添加新工具

1. 在 `app/tools/` 目录下创建新工具模块
2. 在 `app/tools/__init__.py` 中：
   - 定义工具 schema
   - 实现工具函数
   - 注册到 `TOOL_REGISTRY`

示例：

```python
# app/tools/weather.py
def get_weather(city: str) -> dict:
    # 实现...
    return {"city": city, "temp": 20}

# app/tools/__init__.py
WEATHER_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "weather",
        "description": "Get weather for a city",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
        }
    }
}

TOOL_REGISTRY = {
    "weather": get_weather,
    # ...
}

AVAILABLE_TOOLS = [STOCK_PRICE_TOOL_SCHEMA, WEATHER_TOOL_SCHEMA]
```

## 许可证

MIT