import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import InputBox from "./InputBox.jsx";

// Ask (RAG) window — same layout as ChatWindow, with source citations displayed
// below each assistant message, and a reflection status badge.

function AskMessage({ role, content, sources, passedReflection }) {
  const roleLabel =
    role === "user" ? "You" : role === "error" ? "Error" : "Assistant";

  return (
    <div className={`message message--${role}`}>
      <div className="message__role">{roleLabel}</div>
      <div className="message__content">
        {role === "assistant" ? (
          <div className="markdown-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content || ""}
            </ReactMarkdown>
          </div>
        ) : (
          content
        )}
      </div>

      {/* Source citations — only shown on assistant messages with at least one source */}
      {role === "assistant" && sources && sources.length > 0 && (
        <div className="ask-message__sources">
          <span className="ask-message__sources-label">📎 来源 chunk：</span>
          <ul className="ask-message__sources-list">
            {sources.map((id) => (
              <li key={id} className="ask-message__source-item">
                <code>{id}</code>
              </li>
            ))}
          </ul>
          {passedReflection !== null && passedReflection !== undefined && (
            <span
              className={`ask-message__reflection-badge ${
                passedReflection
                  ? "ask-message__reflection-badge--pass"
                  : "ask-message__reflection-badge--fail"
              }`}
              title={
                passedReflection
                  ? "Reflection 通过（当前为占位实现）"
                  : "Reflection 未通过"
              }
            >
              {passedReflection ? "✓ Reflection" : "✗ Reflection"}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default function AskWindow({ messages, loading, onSend }) {
  const endRef = useRef(null);
  const windowRef = useRef(null);
  const [inputHeight, setInputHeight] = useState(130);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e) => {
      if (!windowRef.current) return;
      const rect = windowRef.current.getBoundingClientRect();
      const newHeight = rect.bottom - e.clientY;
      const minHeight = 72;
      const maxHeight = Math.max(minHeight, rect.height - 120);
      setInputHeight(Math.max(minHeight, Math.min(newHeight, maxHeight)));
    };

    const handleMouseUp = () => setIsDragging(false);

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging]);

  return (
    <section className="chatwindow" ref={windowRef}>
      <div className="chatwindow__messages">
        {messages.length === 0 && !loading && (
          <div className="chatwindow__empty">
            <h1>Ask — 知识库问答</h1>
            <p>
              基于企业知识库检索（ChromaDB + bge-m3）生成答案。
              <br />
              答案仅来源于已导入的文档，并标注 chunk 引用。
              <br />
              若知识库中无相关内容，将直接返回"未找到"，不会调用 LLM。
            </p>
          </div>
        )}

        {messages.map((m, i) => (
          <AskMessage
            key={i}
            role={m.role}
            content={m.content}
            sources={m.sources}
            passedReflection={m.passedReflection}
          />
        ))}

        {loading && (
          <div className="message message--assistant">
            <div className="message__role">Assistant</div>
            <div className="message__content chatwindow__typing">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div
        className={`chatwindow__resizer ${isDragging ? "chatwindow__resizer--active" : ""}`}
        onMouseDown={(e) => { e.preventDefault(); setIsDragging(true); }}
        role="separator"
        aria-orientation="horizontal"
        title="Drag to resize input area"
      >
        <div className="chatwindow__resizer-line" />
      </div>

      <InputBox onSend={onSend} disabled={loading} height={inputHeight} />
    </section>
  );
}
