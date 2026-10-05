// A single chat message bubble. Role is "user" | "assistant" | "error".

export default function Message({ role, content, traceId, onTraceClick }) {
  const roleLabel =
    role === "user" ? "You" : role === "error" ? "Error" : "Assistant";

  return (
    <div className={`message message--${role}`}>
      <div className="message__role">{roleLabel}</div>
      <div className="message__content">{content}</div>
      {role === "assistant" && traceId && (
        <div className="message__trace-id">
          <span className="message__trace-label">trace_id:</span>
          <code
            className="message__trace-code"
            onClick={() => onTraceClick && onTraceClick(traceId)}
            title="View in Trace panel"
          >
            {traceId}
          </code>
        </div>
      )}
    </div>
  );
}
