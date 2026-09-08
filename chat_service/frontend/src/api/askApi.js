// Thin client for the qa_service RAG Ask pipeline.
// Calls /api/ask — distinct from /api/chat (direct LLM, no retrieval).

const ASK_ENDPOINT = "/api/ask";

/**
 * Send a question to the RAG Ask pipeline.
 * @param {string} question
 * @returns {Promise<{answer: string, sources: string[], passed_reflection: boolean|null, error: string|null}>}
 */
export async function askWithRAG(question) {
  const res = await fetch(ASK_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body && body.detail) detail = JSON.stringify(body.detail);
    } catch (_) {
      /* ignore parse error */
    }
    throw new Error(`Request failed: ${detail}`);
  }

  return res.json();
}
