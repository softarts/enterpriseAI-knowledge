import { useState } from "react";

// Bottom input area: textarea + send button.
// Enter sends, Shift+Enter adds a newline. Disabled while a request is loading.

export default function InputBox({ onSend, disabled }) {
  const [value, setValue] = useState("");

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="inputbox">
      <textarea
        className="inputbox__textarea"
        placeholder="Ask anything…  (Enter to send, Shift+Enter for newline)"
        value={value}
        disabled={disabled}
        rows={1}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button
        className="inputbox__send"
        onClick={submit}
        disabled={disabled || !value.trim()}
      >
        {disabled ? "…" : "Send"}
      </button>
    </div>
  );
}
