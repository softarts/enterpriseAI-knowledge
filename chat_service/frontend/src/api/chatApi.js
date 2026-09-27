// Thin client for the chat_service backend.
// The browser only ever calls chat_service — never Hugging Face directly.

const CHAT_ENDPOINT = "/api/chat";
const CONVERSATION_ID_KEY = "enterprise-ai-chat-conversation-id";

function getConversationId() {
  let conversationId = window.sessionStorage.getItem(CONVERSATION_ID_KEY);
  if (!conversationId) {
    conversationId = typeof crypto !== "undefined" && crypto.randomUUID
      ? `conversation-${crypto.randomUUID()}`
      : `conversation-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    window.sessionStorage.setItem(CONVERSATION_ID_KEY, conversationId);
  }
  return conversationId;
}

/**
 * Send a question to the backend Ask flow.
 * @param {string} question
 * @returns {Promise<{answer: string, trace: object, error: string|null}>}
 */
export async function askQuestion(question) {
  const res = await fetch(CHAT_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Conversation-Id": getConversationId(),
    },
    body: JSON.stringify({ question }),
  });

  if (!res.ok) {
    // Try to surface a structured error body; fall back to status text.
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
