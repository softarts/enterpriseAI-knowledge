// A single chat message bubble. Role is "user" | "assistant" | "error".

export default function Message({ role, content }) {
  const roleLabel =
    role === "user" ? "You" : role === "error" ? "Error" : "Assistant";

  return (
    <div className={`message message--${role}`}>
      <div className="message__role">{roleLabel}</div>
      <div className="message__content">{content}</div>
    </div>
  );
}
