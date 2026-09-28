import { useLayoutEffect, useRef, useState } from "react";

// Enter sends, Shift+Enter adds a newline. The textarea grows with its content.

const MAX_TEXTAREA_HEIGHT = 240;

export default function InputBox({ onSend, onStop, loading }) {
  const [value, setValue] = useState("");
  const textareaRef = useRef(null);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const nextHeight = Math.min(textarea.scrollHeight, MAX_TEXTAREA_HEIGHT);
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > MAX_TEXTAREA_HEIGHT ? "auto" : "hidden";
  }, [value]);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
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
        ref={textareaRef}
        className="inputbox__textarea"
        placeholder="Ask anything…  (Enter to send, Shift+Enter for newline)"
        value={value}
        disabled={loading}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      {loading ? (
        <button
          className="inputbox__stop"
          type="button"
          onClick={onStop}
          aria-label="Stop generating"
          title="Stop generating"
        >
          <span className="inputbox__stop-icon" aria-hidden="true" />
        </button>
      ) : (
        <button
          className="inputbox__send"
          type="button"
          onClick={submit}
          disabled={!value.trim()}
          aria-label="Send message"
          title="Send message"
        >
          ↑
        </button>
      )}
    </div>
  );
}
