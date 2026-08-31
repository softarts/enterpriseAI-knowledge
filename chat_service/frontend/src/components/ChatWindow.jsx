import { useEffect, useRef } from "react";
import Message from "./Message.jsx";
import InputBox from "./InputBox.jsx";

// Center pane: scrollable message list + loading indicator + input box.

export default function ChatWindow({ messages, loading, onSend }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <section className="chatwindow">
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

      <InputBox onSend={onSend} disabled={loading} />
    </section>
  );
}
