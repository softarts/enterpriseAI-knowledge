import { useEffect, useRef } from "react";
import Message from "./Message.jsx";
import InputBox from "./InputBox.jsx";

// Message history and composer share one centered content column.

export default function ChatWindow({
  messages,
  loading,
  onSend,
  onStop,
  pendingInterrupt = null,
  onInterruptConfirm,
  conversationId = null,
  onNewConversation,
  onTraceClick = null,
}) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Hide the typing indicator once the streaming assistant message has text.
  const streamingHasText = messages.length > 0 && messages[messages.length - 1]?.content;

  return (
    <section className="chatwindow">
      {/* Which conversation the messages below belong to. The backend scopes
          short-term memory by this id, so it is the handle that ties the
          visible history to its trace rows and log lines. */}
      {conversationId && (
        <div className="chatwindow__conv">
          <span
            className="chatwindow__conv-id"
            title={conversationId}
            aria-label={`Conversation ${conversationId}`}
          >
            {conversationId}
          </span>
          {onNewConversation && (
            <button
              type="button"
              className="chatwindow__conv-new"
              onClick={onNewConversation}
              title="Start a new conversation (clears short-term memory for the next question)"
            >
              New
            </button>
          )}
        </div>
      )}

      <div className="chatwindow__messages" role="log" aria-live="polite">
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
          <Message
            key={i}
            role={m.role}
            content={m.content}
            traceId={m.traceId}
            onTraceClick={onTraceClick}
          />
        ))}

        {loading && !streamingHasText && (
          <div className="message message--assistant">
            <div className="message__role">Assistant</div>
            <div className="message__content chatwindow__typing">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}

        {pendingInterrupt && (
          <div className="chatwindow__interrupt" role="alertdialog">
            <p>{pendingInterrupt.question}</p>
            <div className="chatwindow__interrupt-actions">
              <button type="button" onClick={() => onInterruptConfirm(true)}>
                确认执行
              </button>
              <button type="button" onClick={() => onInterruptConfirm(false)}>
                取消
              </button>
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="chatwindow__composer">
        <InputBox onSend={onSend} onStop={onStop} loading={loading} />
      </div>
    </section>
  );
}
