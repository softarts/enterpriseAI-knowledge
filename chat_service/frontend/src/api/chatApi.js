// Thin client for the chat_service backend.
// The browser only ever calls chat_service — never Hugging Face directly.

const CHAT_ENDPOINT = "/api/chat";
const CONVERSATION_ID_KEY = "enterprise-ai-chat-conversation-id";

// Stable per-tab conversation id, shared by every request. Exported so the UI
// can display which conversation a message or trace row belongs to.
export function getConversationId() {
  let conversationId = window.sessionStorage.getItem(CONVERSATION_ID_KEY);
  if (!conversationId) {
    conversationId = typeof crypto !== "undefined" && crypto.randomUUID
      ? `conversation-${crypto.randomUUID()}`
      : `conversation-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    window.sessionStorage.setItem(CONVERSATION_ID_KEY, conversationId);
  }
  return conversationId;
}

/** Start a fresh conversation (new id), leaving the current history in place. */
export function newConversationId() {
  const conversationId = typeof crypto !== "undefined" && crypto.randomUUID
    ? `conversation-${crypto.randomUUID()}`
    : `conversation-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  window.sessionStorage.setItem(CONVERSATION_ID_KEY, conversationId);
  return conversationId;
}

/**
 * Send a question to the backend Ask flow.
 * @param {string} question
 * @returns {Promise<{answer: string, trace: object, error: string|null}>}
 */
export async function askQuestion(question, { signal } = {}) {
  const res = await fetch(CHAT_ENDPOINT, {
    method: "POST",
    signal,
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

// ---------------------------------------------------------------------------
// Streaming (SSE over POST — EventSource cannot POST, so we parse manually)
// ---------------------------------------------------------------------------

const STREAM_ENDPOINT = "/api/chat/stream";
const RESUME_ENDPOINT = "/api/chat/resume";
const CANCEL_ENDPOINT = "/api/chat/cancel";

/**
 * Parse an SSE byte stream and dispatch parsed events to `onEvent`.
 * SSE framing: `data: {json}\n\n`. Multi-line data is concatenated with \n.
 */
async function consumeSSE(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Frames are separated by a blank line.
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
        onEvent(JSON.parse(payload));
      } catch {
        // Ignore malformed frames rather than breaking the stream.
      }
    }
  }
}

/**
 * Stream one chat turn. `onEvent` receives every protocol event:
 * token / tool_call / tool_result / node_start / interrupt / done / error.
 * Resolves when the server closes the stream.
 */
export async function askQuestionStream(question, { onEvent, signal, tokenScope = "all" } = {}) {
  const res = await fetch(STREAM_ENDPOINT, {
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/json",
      "X-Conversation-Id": getConversationId(),
    },
    body: JSON.stringify({ question, token_scope: tokenScope }),
  });

  if (!res.ok || !res.body) {
    throw new Error(`Stream request failed: ${res.status} ${res.statusText}`);
  }
  await consumeSSE(res, onEvent);
}

/** Resume a turn paused by the HITL gate. `resume` false rejects the tool call. */
export async function resumeStream(resume, { onEvent, signal, tokenScope = "all" } = {}) {
  const res = await fetch(RESUME_ENDPOINT, {
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/json",
      "X-Conversation-Id": getConversationId(),
    },
    body: JSON.stringify({ resume, token_scope: tokenScope }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`Resume request failed: ${res.status} ${res.statusText}`);
  }
  await consumeSSE(res, onEvent);
}

/** Ask the backend to cancel its in-flight graph run for this conversation. */
export async function cancelStream() {
  try {
    await fetch(CANCEL_ENDPOINT, {
      method: "POST",
      headers: { "X-Conversation-Id": getConversationId() },
    });
  } catch {
    // Best-effort: the client abort already closed the connection.
  }
}
