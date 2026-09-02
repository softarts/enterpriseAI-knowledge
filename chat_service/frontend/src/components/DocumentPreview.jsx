import { useState } from "react";

// Simple text reader: renders body with basic formatting.
export default function DocumentPreview({ body }) {
  const [loaded, setLoaded] = useState(false);

  // Split into title + paragraphs for cleaner rendering.
  let raw = "";
  if (typeof body === "string") {
    raw = body;
  } else if (body && typeof body.body === "string") {
    raw = body.body;
  }

  const lines = raw.split("\n");
  const paragraphs = [];
  let currentPara = [];

  function flushPara() {
    if (currentPara.length > 0) {
      // Detect list vs paragraph.
      const firstLine = currentPara[0].trim();
      if (/^\s*[-*+]\s/.test(firstLine)) {
        paragraphs.push({ type: "list", items: currentPara });
      } else if (firstLine.startsWith("```")) {
        // Code block.
        const codeLines = [];
        let inCode = false;
        for (const line of currentPara) {
          if (!inCode && /^\s*```/.test(line)) {
            inCode = true;
          } else if (inCode && /^\s*```/.test(line)) {
            break;
          } else if (inCode) {
            codeLines.push(line);
          }
        }
        paragraphs.push({ type: "code", content: codeLines.join("\n") });
      } else {
        paragraphs.push({ type: "text", text: currentPara.join(" ") });
      }
    }
    currentPara = [];
  }

  for (const line of lines) {
    if (/^\s*$/.test(line)) {
      flushPara();
    } else {
      currentPara.push(line);
    }
  }
  flushPara();

  return (
    <div className="doc-preview">
      {!loaded && (
        <div className="doc-preview__empty">
          <span className="spinner" />
          <span>正在加载文档内容…</span>
        </div>
      )}
      {paragraphs.length === 0 ? (
        <div className="doc-preview__empty">暂无正文内容</div>
      ) : (
        paragraphs.map((p, i) => {
          if (p.type === "text") {
            return (
              <p key={i} className="doc-preview__para">
                {p.text}
              </p>
            );
          }
          if (p.type === "list") {
            return (
              <ul key={i} className="doc-preview__list">
                {p.items.map((item, j) => (
                  <li key={j}>{item.trim()}</li>
                ))}
              </ul>
            );
          }
          if (p.type === "code") {
            return (
              <pre key={i} className="doc-preview__code">
                <code>{p.content}</code>
              </pre>
            );
          }
          return null;
        })
      )}
    </div>
  );
}