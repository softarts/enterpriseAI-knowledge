import { useState } from "react";
import Layout from "./components/Layout.jsx";
import ChatWindow from "./components/ChatWindow.jsx";
import { askQuestion } from "./api/chatApi.js";

// Top-level state: messages, loading, latest trace, and pane collapse flags.
// Kept intentionally simple (no router, no store) for the v1 playground shell.

export default function App() {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [trace, setTrace] = useState(null);

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

  return (
    <Layout
      sidebarCollapsed={sidebarCollapsed}
      onToggleSidebar={() => setSidebarCollapsed((v) => !v)}
      traceCollapsed={traceCollapsed}
      onToggleTrace={() => setTraceCollapsed((v) => !v)}
      trace={trace}
    >
      <ChatWindow messages={messages} loading={loading} onSend={handleSend} />
    </Layout>
  );
}
