# Task Completion Report — chat_service (Enterprise AI Playground)

- **Date:** 2026-08-25
- **Status:** ✅ Success — front and back end run and were verified against the real Hugging Face API.
- **Goal:** Add a standalone `chat_service` implementing a minimal Enterprise AI Playground Web UI (three-pane, ChatGPT-desktop style), with a first Ask flow that goes `Browser → chat_service → Hugging Face Cloud LLM → Answer + Trace`. No RAG / Chroma / MCP yet.

---

## 1. What was implemented

### Backend — `chat_service/` (FastAPI, reuses the existing Python stack)

| File | Responsibility |
|---|---|
| `chat_service/config.py` | Settings from env. Reads `HF_TOKEN` **only** from the environment (never hardcoded, never sent to the frontend). Model `openai/gpt-oss-120b`, port `8100`, CORS origins. |
| `chat_service/models.py` | Pydantic `ChatRequest{question}` / `ChatResponse{answer, trace, error}`. `trace` is an open dict for extensibility. |
| `chat_service/trace.py` | `TraceBuilder` — assembles the extensible trace: `trace_id`, timings, ordered `steps[]`, and named sections (`request`, `llm`, `response`). New pipeline stages just add steps. |
| `chat_service/llm/hf_client.py` | `HuggingFaceLLM` — the verified pattern: `InferenceClient(api_key=HF_TOKEN, provider="auto")` + `chat.completions.create(model="openai/gpt-oss-120b", ...)`. Raises `HFTokenMissingError` when the token is absent. |
| `chat_service/services/chat_service.py` | `ChatService.ask()` — orchestrates request → LLM → response, records each step, catches token/upstream errors into the trace. Contains the explicit, commented **RAG seam** for the next stage. |
| `chat_service/api/routes_chat.py` | `GET /api/health`, `POST /api/chat`. |
| `chat_service/main.py` | FastAPI app + CORS middleware. |
| `chat_service/run.py` | `python -m chat_service.run` (uvicorn on :8100). |

### Frontend — `chat_service/frontend/` (React + Vite)

| File | Responsibility |
|---|---|
| `package.json`, `vite.config.js`, `index.html` | Vite app; dev server on `:5173` proxies `/api` → `http://localhost:8100` (browser stays same-origin; never calls HF directly). |
| `src/App.jsx` | Top-level state: messages, loading, latest trace, pane collapse flags. |
| `src/components/Layout.jsx` | Three-pane grid shell; center auto-resizes when either side pane collapses. |
| `src/components/Sidebar.jsx` | Left pane, collapsible; Chat / Documents / Settings menu entries (placeholders). |
| `src/components/ChatWindow.jsx` | Center pane: message list, loading (typing) indicator, input box, auto-scroll. |
| `src/components/Message.jsx` | User / assistant / error bubble. |
| `src/components/InputBox.jsx` | Textarea + send; Enter to send, Shift+Enter newline; disabled while loading. |
| `src/components/TracePanel.jsx` | Right pane, collapsible; renders the **real** backend trace (steps + detail + timings). No mock data. |
| `src/api/chatApi.js` | `askQuestion()` → `POST /api/chat`. |
| `src/styles.css` | Dark AI-developer-playground styling; three-pane CSS grid. |

### Other changes
- `requirements.txt` — added `huggingface_hub>=0.24.0`.
- `.gitignore` — ignore `chat_service/frontend/node_modules/` and `dist/`.

No changes were made to `doc_service`, `vector_service`, or the MCP core.

---

## 2. Trace structure (extensible)

```json
{
  "trace_id": "…",
  "started_at": "ISO-8601",
  "finished_at": "ISO-8601",
  "duration_ms": 1835.45,
  "steps": [
    { "name": "request",  "status": "ok", "detail": { … }, "duration_ms": null },
    { "name": "llm",      "status": "ok", "detail": { "provider": "huggingface", "model": "…", "usage": { … } }, "duration_ms": 1835.43 },
    { "name": "response", "status": "ok", "detail": { "answer_chars": 6 }, "duration_ms": null }
  ],
  "request":  { … },
  "llm":      { … },
  "response": { … }
}
```

Future stages (retrieval, context assembly, reranker, agent/ReAct) append additional steps/sections; the UI renders whatever steps exist, so no UI change is needed to surface them.

---

## 3. How to run

Backend (terminal 1):
```powershell
# from repo root; HF_TOKEN must be set in the environment
$env:HF_TOKEN = "hf_xxx"
python -m chat_service.run
# -> http://localhost:8100  (GET /api/health, POST /api/chat)
```

Frontend (terminal 2):
```powershell
cd chat_service/frontend
npm install      # first time only
npm run dev
# -> http://localhost:5173   (open in browser)
```

Open `http://localhost:5173`, type a question, press Enter. The answer appears in the center; the right Trace panel shows the real execution steps.

---

## 4. Verification results

All checks passed against the **real** Hugging Face API (model `openai/gpt-oss-120b`):

1. **Backend import** — app loads, routes present: `/api/health`, `/api/chat`.
2. **`GET /api/health`** → `{"service":"chat-service","model":"openai/gpt-oss-120b","hf_token_configured":true}`.
3. **`POST /api/chat` (direct :8100)** — question "Say hello in one short sentence" → real answer `"Hello!"`, trace with `request/llm/response` all `ok`, token usage populated (`total_tokens: 133`).
4. **Full browser path (Vite proxy `localhost:5173/api/chat` → :8100 → HF)** — question "Reply with the single word: pong" → real answer `"pong"`, trace steps `request(ok), llm(ok), response(ok)`.
5. **Error path** — with no `HF_TOKEN`, response carries a structured `error` string and the `llm` trace step is marked `status: "error"`, so the UI shows an error bubble + error step.
6. **`npm install`** — 63 packages installed; `npm run dev` served Vite on :5173.

UI states covered: loading (typing indicator + disabled input), error (red bubble + error trace step), normal answer (assistant bubble + ok trace).

---

## 5. Not implemented (intentionally out of scope)

RAG, Chroma retrieval, BM25, hybrid search, reranker, MCP integration, Agent / ReAct / reflection, authentication, database, and chat history are **not** implemented. The Ask flow is a direct single-turn LLM call.

---

## 6. Extension point reserved for RAG / vector_service

`chat_service/services/chat_service.py` contains an explicit, commented **RAG seam** between the `request` and `llm` steps. When enabling RAG:
1. Call retrieval (e.g. `vector_service.search(question, top_k)` behind a thin client) before the LLM.
2. Add a `retrieval` (and optional `context`) trace step — the UI will render it automatically.
3. Prepend the assembled context to the LLM prompt.

No change to the public API (`POST /api/chat`), the response shape, or the frontend is required to add retrieval — only new trace steps appear.

---

## 7. Notes / follow-ups

- The token used for verification came from the developer's local environment; it is never written into code or the frontend. Rotate/scope tokens as needed.
- Vite dev server binds to `localhost` (IPv6 `::1`); use `http://localhost:5173`, not `127.0.0.1`, in local testing.
- Suggested next steps: add a thin `RetrievalClient` abstraction over `vector_service`, then wire the RAG seam; consider streaming responses and multi-turn history later.
