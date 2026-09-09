import { useState } from "react";
import Layout from "./components/Layout.jsx";
import ChatWindow from "./components/ChatWindow.jsx";
import AskWindow from "./components/AskWindow.jsx";
import ImportPage from "./components/ImportPage.jsx";
import BrowsePage from "./components/BrowsePage.jsx";
import TaskPage from "./components/TaskPage.jsx";
import { askQuestion } from "./api/chatApi.js";
import { askWithRAG } from "./api/askApi.js";

// Top-level state: active view, messages, loading, trace, pane collapse.
// Kept intentionally simple: no router, no store.

export default function App() {
  const [activeView, setActiveView] = useState("chat");

  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [trace, setTrace] = useState(null);
  const [askTrace, setAskTrace] = useState(null);

  // Ask (RAG) — independent state so switching views preserves history
  const [askMessages, setAskMessages] = useState([]);
  const [askLoading, setAskLoading] = useState(false);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [traceCollapsed, setTraceCollapsed] = useState(false);

  async function handleSend(question) {
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const data = await askQuestion(question);

      // Always show the trace, even for backend-reported errors.
      setTrace(data.trace || null);

      if (data.error) {
        setMessages((prev) => [
          ...prev,
          { role: "error", content: data.error },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.answer || "(empty answer)" },
        ]);
      }
    } catch (err) {
      // Network / transport level failure (backend down, etc.).
      setMessages((prev) => [
        ...prev,
        { role: "error", content: err.message || "Request failed." },
      ]);
    } finally {
      setLoading(false);
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

  return (
    <Layout
      sidebarCollapsed={sidebarCollapsed}
      onToggleSidebar={() => setSidebarCollapsed((v) => !v)}
      traceCollapsed={traceCollapsed}
      onToggleTrace={() => setTraceCollapsed((v) => !v)}
      trace={activeView === "ask" ? askTrace : trace}
      activeView={activeView}
      onViewChange={setActiveView}
      showTrace={activeView === "chat" || activeView === "ask"}
    >
      {activeView === "chat" ? (
        <ChatWindow messages={messages} loading={loading} onSend={handleSend} />
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
