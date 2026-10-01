import { useRef, useState } from "react";
import Layout from "./components/Layout.jsx";
import ChatWindow from "./components/ChatWindow.jsx";
import AskWindow from "./components/AskWindow.jsx";
import ImportPage from "./components/ImportPage.jsx";
import BrowsePage from "./components/BrowsePage.jsx";
import TaskPage from "./components/TaskPage.jsx";
import { askQuestionStream, cancelStream, resumeStream } from "./api/chatApi.js";
import { askWithRAG } from "./api/askApi.js";

// Top-level state: active view, messages, loading, trace, pane collapse.
// Kept intentionally simple: no router, no store.

export default function App() {
  const [activeView, setActiveView] = useState("chat");

  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [askTrace, setAskTrace] = useState(null);
  const chatRequestRef = useRef(null);

  // Streaming state: the in-flight assistant message index, tool cards and
  // any pending HITL confirmation.
  const [toolCards, setToolCards] = useState([]);
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
        setToolCards((prev) => [
          ...prev,
          { id: event.id, name: event.name, args: event.args, status: "running" },
        ]);
        break;
      case "tool_result":
        setToolCards((prev) =>
          prev.map((card) =>
            card.id === event.id
              ? { ...card, status: event.status, content: event.content }
              : card
          )
        );
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
    setToolCards([]);
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

  // Tool call/result activity is shown in the Trace panel, not inline in the
  // chat window — the chat window should only show the final answer.
  const chatTrace =
    toolCards.length > 0
      ? {
          steps: toolCards.map((card) => ({
            name: card.name,
            status:
              card.status === "running"
                ? "running"
                : card.status === "error"
                ? "error"
                : "ok",
            detail: {
              args: card.args,
              ...(card.content ? { result: card.content.slice(0, 2000) } : {}),
            },
          })),
        }
      : null;

  return (
    <Layout
      sidebarCollapsed={sidebarCollapsed}
      onToggleSidebar={() => setSidebarCollapsed((v) => !v)}
      traceCollapsed={traceCollapsed}
      onToggleTrace={() => setTraceCollapsed((v) => !v)}
      trace={activeView === "ask" ? askTrace : activeView === "chat" ? chatTrace : null}
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
