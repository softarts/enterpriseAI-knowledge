import { useMemo, useRef, useState } from "react";
import Layout from "./components/Layout.jsx";
import ChatWindow from "./components/ChatWindow.jsx";
import AskWindow from "./components/AskWindow.jsx";
import ImportPage from "./components/ImportPage.jsx";
import BrowsePage from "./components/BrowsePage.jsx";
import TaskPage from "./components/TaskPage.jsx";
import {
  askQuestionStream,
  cancelStream,
  getConversationId,
  newConversationId,
  resumeStream,
} from "./api/chatApi.js";
import { askWithRAG } from "./api/askApi.js";

// Top-level state: active view, messages, loading, trace, pane collapse.
// Kept intentionally simple: no router, no store.

export default function App() {
  const [activeView, setActiveView] = useState("chat");

  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [askTrace, setAskTrace] = useState(null);
  const chatRequestRef = useRef(null);
  // Which conversation the visible history belongs to. Backend rows carry
  // their own id; this covers the header and messages sent before the first
  // trace row exists.
  const [conversationId, setConversationId] = useState(() => getConversationId());

  // Streaming state: the in-flight assistant message index, the ordered
  // activity timeline (tool_call/tool_result + trace entries, in arrival
  // order) feeding the Trace panel, and any pending HITL confirmation.
  const [timeline, setTimeline] = useState([]);
  // Traces from earlier conversations, kept so starting a new conversation
  // archives rather than discards them. Each entry is a self-contained
  // {conversation_id, steps} snapshot.
  const [archivedTraces, setArchivedTraces] = useState([]);
  const [activeTraceOpen, setActiveTraceOpen] = useState(true);
  const [pendingInterrupt, setPendingInterrupt] = useState(null);
  const streamingIndexRef = useRef(null);

  // Ask (RAG) — independent state so switching views preserves history
  const [askMessages, setAskMessages] = useState([]);
  const [askLoading, setAskLoading] = useState(false);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [traceCollapsed, setTraceCollapsed] = useState(false);

  // Append streamed text to the assistant message being built.
  function appendToStreaming(text) {
    const index = streamingIndexRef.current;
    if (index == null) return;
    setMessages((prev) =>
      prev.map((m, i) => (i === index ? { ...m, content: m.content + text } : m))
    );
  }

  function handleStreamEvent(event) {
    switch (event.type) {
      case "token":
        appendToStreaming(event.text || "");
        break;
      case "node_start":
        break; // reserved for step indicators
      case "tool_call":
        setTimeline((prev) => [
          ...prev,
          {
            kind: "tool",
            id: event.id,
            name: event.name,
            args: event.args,
            status: "running",
          },
        ]);
        break;
      case "tool_result":
        setTimeline((prev) =>
          prev.map((item) =>
            item.kind === "tool" && item.id === event.id
              ? { ...item, status: event.status, content: event.content }
              : item
          )
        );
        break;
      case "trace":
        // Aggregated LLM calls (kind "llm", carrying the real request and the
        // merged response), tool executions (kind "tool"), the httpx
        // request/response attempts (kind "http") and local node spans
        // (kind "local"). Keyed by the backend's stable `seq`: LLM and tool
        // rows arrive twice — once while still in flight, once finalized —
        // and the second one replaces the first.
        if (event.conversation_id) setConversationId(event.conversation_id);
        setTimeline((prev) => {
          const row = {
            seq: event.seq,
            kind: event.kind, // "llm" | "tool" | "http" | "local"
            name: event.name,
            status: event.status,
            detail: event.detail,
            durationMs: event.duration_ms,
            conversationId: event.conversation_id,
            llmCallId: event.llm_call_id,
            toolCallId: event.tool_call_id,
          };
          if (row.seq == null) return [...prev, row];
          const at = prev.findIndex((item) => item.seq === row.seq);
          if (at === -1) return [...prev, row];
          const next = [...prev];
          next[at] = row;
          return next;
        });
        break;
      case "interrupt":
        setPendingInterrupt({
          question: event.question,
          resumeKey: event.resume_key,
          threadId: event.thread_id,
        });
        setLoading(false);
        break;
      case "error":
        setMessages((prev) => [
          ...prev,
          { role: "error", content: event.message || "Stream error" },
        ]);
        break;
      case "done":
        setLoading(false);
        break;
      default:
        break;
    }
  }

  async function handleSend(question) {
    const controller = new AbortController();
    chatRequestRef.current = controller;
    setMessages((prev) => [
      ...prev,
      { role: "user", content: question },
      { role: "assistant", content: "" },
    ]);
    // The assistant placeholder is the last message.
    streamingIndexRef.current = null;
    setLoading(true);
    setTimeline([]);
    setPendingInterrupt(null);

    // Resolve the placeholder index after the state update is queued.
    const placeholderIndex = messages.length + 1;
    streamingIndexRef.current = placeholderIndex;

    try {
      await askQuestionStream(question, {
        signal: controller.signal,
        onEvent: handleStreamEvent,
      });
    } catch (err) {
      if (err.name === "AbortError") {
        appendToStreaming("\n[已停止]");
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "error", content: err.message || "Stream failed." },
        ]);
      }
    } finally {
      if (chatRequestRef.current === controller) {
        chatRequestRef.current = null;
        streamingIndexRef.current = null;
        setLoading(false);
      }
    }
  }

  function handleStopChat() {
    const controller = chatRequestRef.current;
    if (controller) {
      chatRequestRef.current = null;
      controller.abort();
      // Also stop the server-side graph run.
      cancelStream();
    }
    setLoading(false);
    streamingIndexRef.current = null;
  }

  // Start a new conversation: fresh id, empty timeline. The visible messages
  // are left alone so the previous turn stays readable — the backend keys
  // short-term memory by conversation id, so the next question starts clean.
  // The outgoing trace is *archived* (collapsed in the panel), not discarded:
  // it is usually the reason you started a new conversation in the first
  // place, and it stays attributable to its own conversation id.
  function handleNewConversation() {
    if (chatRequestRef.current) {
      chatRequestRef.current.abort();
      chatRequestRef.current = null;
      cancelStream();
    }
    if (timeline.length > 0) {
      const snapshot = buildTraceFromTimeline(timeline);
      setArchivedTraces((prev) =>
        [
          ...prev,
          {
            key: `${snapshot.conversationId}-${prev.length}`,
            conversationId: snapshot.conversationId,
            trace: snapshot,
          },
        ].slice(-MAX_ARCHIVED_TRACES)
      );
    }
    setConversationId(newConversationId());
    setTimeline([]);
    setActiveTraceOpen(true);
    setPendingInterrupt(null);
    setLoading(false);
    streamingIndexRef.current = null;
  }

  async function handleInterruptConfirm(resume) {
    setPendingInterrupt(null);
    setLoading(true);
    const controller = new AbortController();
    chatRequestRef.current = controller;
    try {
      await resumeStream(resume, {
        signal: controller.signal,
        onEvent: handleStreamEvent,
      });
    } catch (err) {
      if (err.name !== "AbortError") {
        setMessages((prev) => [
          ...prev,
          { role: "error", content: err.message || "Resume failed." },
        ]);
      }
    } finally {
      if (chatRequestRef.current === controller) {
        chatRequestRef.current = null;
        setLoading(false);
      }
    }
  }

  async function handleAskSend(question) {
    setAskMessages((prev) => [...prev, { role: "user", content: question }]);
    setAskLoading(true);

    try {
      const data = await askWithRAG(question);
      setAskTrace(data.trace || null);

      if (data.error) {
        setAskMessages((prev) => [
          ...prev,
          { role: "error", content: data.error },
        ]);
      } else {
        setAskMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.answer || "(empty answer)",
            sources: data.sources || [],
            passedReflection: data.passed_reflection ?? null,
          },
        ]);
      }
    } catch (err) {
      setAskMessages((prev) => [
        ...prev,
        { role: "error", content: err.message || "Request failed." },
      ]);
    } finally {
      setAskLoading(false);
    }
  }

  // How many finished conversations' traces to keep collapsed in the panel.
// Bounded because each one holds full request/response payloads.
const MAX_ARCHIVED_TRACES = 5;

// Convert the event timeline into the `{steps}` shape TracePanel renders.
// Shared by the live trace and the archived snapshots so both render
// identically.
function buildTraceFromTimeline(timeline) {
  return {
    conversationId:
      timeline.find((item) => item.conversationId)?.conversationId || null,
    steps: timeline.map((item) => {
      if (item.kind === "tool" && item.toolCallId && !item.detail) {
        // Legacy tool_call/tool_result pair from the graph, not a call_trace
        // "tool" entry.
        return {
          kind: "tool",
          name: item.name,
          status:
            item.status === "running"
              ? "running"
              : item.status === "error"
                ? "error"
                : "ok",
          detail: {
            args: item.args,
            ...(item.content ? { result: item.content } : {}),
          },
        };
      }
      return {
        kind: item.kind, // "llm" | "tool" | "http" | "local"
        name: item.name,
        status: item.status,
        detail: item.detail,
        duration_ms: item.durationMs,
        conversation_id: item.conversationId,
      };
    }),
  };
}

// Tool calls, aggregated LLM calls, HTTP (LLM API) attempts and local
  // function spans are all shown in the Trace panel, not inline in the chat
  // window — the chat window should only show the final answer.
  const chatTrace = useMemo(
    () => (timeline.length > 0 ? buildTraceFromTimeline(timeline) : null),
    [timeline]
  );

  return (
    <Layout
      sidebarCollapsed={sidebarCollapsed}
      onToggleSidebar={() => setSidebarCollapsed((v) => !v)}
      traceCollapsed={traceCollapsed}
      onToggleTrace={() => setTraceCollapsed((v) => !v)}
      trace={activeView === "ask" ? askTrace : activeView === "chat" ? chatTrace : null}
      conversationId={conversationId}
      archivedTraces={activeView === "chat" ? archivedTraces : []}
      activeTraceOpen={activeTraceOpen}
      onToggleActiveTrace={() => setActiveTraceOpen((v) => !v)}
      activeView={activeView}
      onViewChange={setActiveView}
      showTrace={activeView === "chat" || activeView === "ask"}
    >
      {activeView === "chat" ? (
        <ChatWindow
          messages={messages}
          loading={loading}
          onSend={handleSend}
          onStop={handleStopChat}
          pendingInterrupt={pendingInterrupt}
          onInterruptConfirm={handleInterruptConfirm}
          conversationId={conversationId}
          onNewConversation={handleNewConversation}
        />
      ) : activeView === "ask" ? (
        <AskWindow messages={askMessages} loading={askLoading} onSend={handleAskSend} />
      ) : activeView === "import" ? (
        <ImportPage onOpenTasks={() => setActiveView("tasks")} />
      ) : activeView === "tasks" ? (
        <TaskPage />
      ) : (
        <BrowsePage />
      )}
    </Layout>
  );
}
