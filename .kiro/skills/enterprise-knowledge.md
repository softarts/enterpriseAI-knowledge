---
inclusion: manual
---

# Enterprise Knowledge (MCP-only retrieval)

Use this skill whenever the user asks to "use enterprise-knowledge mcp",
"use enterprise-kb mcp", or otherwise requests an answer from the enterprise
knowledge base. It defines the ONLY approved way to retrieve that knowledge.

## Hard rule: go through MCP

Enterprise knowledge MUST be retrieved by calling the `enterprise-kb` MCP
server's tools. This is a requirement, not a preference.

You MUST:
- Call the MCP tool `search_knowledge(query, top_k=5)` (semantic / embedding
  retrieval) to get grounding context.
- Use the other `enterprise-kb` MCP tools when appropriate:
  `query_documents` (keyword search), `list_documents`, `get_document`.

You MUST NOT (these all violate this skill):
- Call the Python functions in `doc_service/mcp/server.py` in-process
  (e.g. `from doc_service.mcp.server import search_knowledge`).
- Call the FastAPI REST endpoints directly (`http://localhost:8000/...`).
- Query the `embedding_service` / `embedding/*.json` or run
  `search_by_similarity` yourself.
- Read the OKF files under `generated/` or `all_documents/` to answer.
- Hand-craft raw HTTP requests to `/mcp` (the transport needs an MCP session
  handshake; use the MCP tool binding instead).

If the answer did not come through an `enterprise-kb` MCP tool call, it does not
count as satisfying an "enterprise-knowledge mcp" request.

## Correct procedure

1. Call `search_knowledge` via MCP with the user's question and `top_k` (default 5).
2. Read the returned ranked chunks (`rank`, `score`, `document_id`, `heading`,
   `chunk_id`, `title`, `source_path`, `text`).
3. Synthesize the answer using ONLY the returned context. Do not add outside
   knowledge. If context is insufficient, say so explicitly.
4. Cite the sources you used, referencing them by `[SOURCE <rank>]` and/or their
   heading and document.
5. If more depth is needed on one document, call `get_document(document_id)`
   via MCP for the full text.

MCP returns context only; the final answer is synthesized by the agent (Kiro),
never by the MCP server.

## If the MCP tools are unavailable

Do not silently fall back to direct API or in-process calls. Instead:
1. Check whether the `enterprise-kb` server is reachable (it is configured in
   `.kiro/settings/mcp.json` at `http://localhost:8001/mcp`).
2. If it is not running, start it once: `python -m doc_service.mcp_main`
   (REST on :8000, MCP on :8001). If the ports are already bound, an instance is
   already running — reconnect the MCP server in Kiro rather than starting a new one.
3. Retry the MCP tool call. Only report failure if the MCP call itself cannot be made.

## Backend note

`search_knowledge` is backed by SBERT embedding (vector) retrieval behind the
shared `Retriever` protocol; `query_documents` is backed by keyword retrieval.
The retrieval backend is decoupled from the MCP interface, so a future vector DB
(e.g. Chroma) can be swapped in without changing how these tools are called.
