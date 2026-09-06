import { useEffect, useRef, useState } from "react";
import Message from "./Message.jsx";
import InputBox from "./InputBox.jsx";

// Center pane: scrollable message list + loading indicator + input box with draggable height resizer.

export default function ChatWindow({ messages, loading, onSend }) {
  const endRef = useRef(null);
  const chatWindowRef = useRef(null);
  const [inputHeight, setInputHeight] = useState(130);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e) => {
      if (!chatWindowRef.current) return;
      const rect = chatWindowRef.current.getBoundingClientRect();
      const newHeight = rect.bottom - e.clientY;
      const minHeight = 72;
      const maxHeight = Math.max(minHeight, rect.height - 120);
      setInputHeight(Math.max(minHeight, Math.min(newHeight, maxHeight)));
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

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

  const handleMouseDown = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  return (
    <section className="chatwindow" ref={chatWindowRef}>
      <div className="chatwindow__messages">
        {messages.length === 0 && !loading && (
          <div className="chatwindow__empty">
            <h1>Enterprise AI Playground</h1>
            <p>
              Ask a question to call the LLM through <code>chat_service</code>.
              The Trace panel on the right shows the real execution steps for
              each request.
            </p>
          </div>
        )}

        {messages.map((m, i) => (
          <Message key={i} role={m.role} content={m.content} />
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
        onMouseDown={handleMouseDown}
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
