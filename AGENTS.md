# Repository Development Instructions

## Python runtime compatibility

The supported Python runtime is Python 3.14.

- All new and modified Python code must be compatible with Python 3.14.
- Use the virtual environment at the repository root (`.venv-py314`) for all
  installs and test runs; the Homebrew interpreter is PEP 668 protected and
  will refuse direct `pip install`.
- Run tests with `.venv-py314/bin/python -m unittest ...` from the repository root.
- langchain-core 1.x / langgraph 1.x are required for the streaming chat
  endpoints; earlier LangGraph releases do not support custom stream writers.

```bash
.venv-py314/bin/python -m py_compile path/to/module.py
.venv-py314/bin/python -m unittest discover -s <module>/tests -t .
```

## Agentic tool-call guardrails

- Any tool that can be called repeatedly inside an agentic tool-calling loop
  (e.g. a LangGraph `agent -> tools -> agent` cycle) must ship with an explicit
  per-turn call budget, enforced as a **mechanical hard stop** — block the call,
  or invoke the model with that tool unbound so it is physically unable to call
  it again — not a prompt or tool-result message that merely asks the model to
  stop. In-context nudges are a documented anti-pattern: models have been
  observed to ignore "limit reached" messages and keep retrying regardless
  (see e.g. [agno-agi/agno#8304](https://github.com/agno-agi/agno/issues/8304),
  ~4000 repeated tool calls before the framework gave up). A global graph-level
  `recursion_limit` is a crash-backstop for runaway graphs, not a substitute for
  a per-tool budget — it only cuts the conversation off with an error after
  many wasted round trips, instead of letting the agent answer with what it has.
  See `langchain_agent/app/graph.py`'s `create_route_after_hitl` /
  `create_force_finalize_node` / `create_async_force_finalize_node` for the
  reference implementation (caps `web_search` by routing to a no-tools agent
  node instead of `tools` once the budget is spent), and
  `chat_service/README.md`'s "`web_search` 每轮调用预算" and "`should_continue`
  路由机制" sections for the full rationale and the mechanism's limits.
- **"No tools bound" does not guarantee tool-call-free output.** Some
  tool-trained models (observed with an NVIDIA-hosted model in this project)
  keep emitting their native tool-call syntax as plain response *text* —
  e.g. a raw `<tool_call><function=web_search>...` block — even with no
  `tools` schema attached to the request, especially once the conversation
  history is full of prior tool_calls/ToolMessage turns. Any node meant to
  force a tool-free answer must validate the output for leaked tool-call
  markup and retry/fall back rather than trust the absence of a bound schema
  (see `_LEAKED_TOOL_CALL_PATTERN` in `graph.py`).
- **Never stream a response before it's validated.** A streaming node that
  writes tokens via `get_stream_writer()` as they arrive cannot take them back
  — by the time validation would run, a leaked tool-call block is already on
  the user's screen. `create_async_force_finalize_node` buffers the full
  response, validates it, retries once if needed, and only then writes it to
  the stream in one shot — a deliberate (and in this one spot, acceptable)
  trade of true token-by-token streaming for correctness.
- Tunable agent/runtime parameters (step limits, per-tool call budgets, feature
  toggles) belong in `langchain_agent/app/config.py`, the existing single
  definition point for this kind of setting — don't add new ad hoc
  `os.environ.get(...)` reads for agent behavior scattered across other call
  sites.
- This mirrors guardrails already shipped in the Copilot VS Code extension
  (`chat.agent.maxRequests` as the global step cap, `chat.agent.networkFilter` +
  allow/deny domain lists as a per-tool network budget) — use it as the model
  for what "enough guardrails" looks like when adding a new tool.

## Test placement

- Keep tests under the `test/` or `tests/` directory of the module they test.
- Do not create or use a repository-root `test/` or `tests/` directory for new tests.
- Run module tests from the repository root using their module-relative path.
