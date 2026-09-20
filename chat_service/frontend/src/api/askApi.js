// Thin client for the qa_service RAG Ask pipeline.
// Calls /api/ask — distinct from /api/chat (direct LLM, no retrieval).

const ASK_ENDPOINT = "/api/ask";
const USER_ID_KEY = "enterprise-ai-user-id";
const CONVERSATION_ID_KEY = "enterprise-ai-conversation-id";

function createId(prefix) {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function getStoredId(storage, key, prefix) {
  let id = storage.getItem(key);
  if (!id) {
    id = createId(prefix);
    storage.setItem(key, id);
  }
  return id;
}

function getAskIdentity() {
  return {
    userId: getStoredId(window.localStorage, USER_ID_KEY, "user"),
    conversationId: getStoredId(window.sessionStorage, CONVERSATION_ID_KEY, "conversation"),
  };
}

/**
 * Send a question to the RAG Ask pipeline.
 * @param {string} question
 * @returns {Promise<{answer: string, sources: string[], passed_reflection: boolean|null, trace: object, error: string|null}>}
 */
export async function askWithRAG(question) {
  const { userId, conversationId } = getAskIdentity();
  const res = await fetch(ASK_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": userId,
      "X-Conversation-Id": conversationId,
    },
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
