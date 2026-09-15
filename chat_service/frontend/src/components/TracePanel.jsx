import { useState } from "react";

// Right pane: Verbose / Trace panel. Renders the REAL trace object returned by
// the backend for the most recent request — no mocked content. As the backend
// pipeline grows (retrieval, rerank, reflection...), new steps appear here
// automatically because we render whatever `steps` and sections the trace has.

// ─── Raw output block with copy-to-clipboard ─────────────────────────────────
function RawOutput({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div className="trace-raw-output">
      <div className="trace-raw-output__header">
        <span className="trace-raw-output__label">Raw Output</span>
        <button className="trace-raw-output__copy" onClick={handleCopy}>
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <pre className="trace-raw-output__body">{text}</pre>
    </div>
  );
}

// ─── Generic key-value metadata table ────────────────────────────────────────
function MetaTable({ entries }) {
  return (
    <table className="trace-meta-table">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k}>
            <td className="trace-meta-table__k">{k}</td>
            <td className="trace-meta-table__v">{String(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ─── Structured LLM Generation step ──────────────────────────────────────────
function LlmStepDetail({ detail }) {
  const [rawOpen, setRawOpen] = useState(true);

  const inputEntries = [
    ["model", detail.model],
    ["max_tokens", detail.max_tokens],
    ["thinking_enabled", detail.thinking_enabled],
    ["question_chars", detail.question_chars],
    ["context_chars", detail.context_chars],
  ].filter(([, v]) => v !== undefined && v !== null);

  const metaEntries = [
    ["answer_chars", detail.answer_chars],
  ].filter(([, v]) => v !== undefined && v !== null);

  return (
    <div className="trace-step__sections">
      {/* ── Request / Input ── */}
      {inputEntries.length > 0 && (
        <div className="trace-section">
          <div className="trace-section__title">Request / Input</div>
          <MetaTable entries={inputEntries} />
        </div>
      )}

      {/* ── Raw Generation Output ── */}
      {detail.raw_output != null && (
        <div className="trace-section">
          <button
            className="trace-section__collapsible"
            onClick={() => setRawOpen((v) => !v)}
            aria-expanded={rawOpen}
          >
            <span className="trace-section__title">Raw Generation Output</span>
            <span className="trace-section__chevron">{rawOpen ? "▾" : "▸"}</span>
          </button>
          {rawOpen && <RawOutput text={detail.raw_output} />}
        </div>
      )}

      {/* ── Metadata ── */}
      {metaEntries.length > 0 && (
        <div className="trace-section">
          <div className="trace-section__title">Metadata</div>
          <MetaTable entries={metaEntries} />
        </div>
      )}
    </div>
  );
}

// ─── Generic step row (collapsible; structured for llm step) ─────────────────
function StepRow({ step }) {
  const [expanded, setExpanded] = useState(true);
  const statusClass = `trace-step--${step.status || "ok"}`;
  const isLlm = step.name === "llm";

  return (
    <div className={`trace-step ${statusClass}`}>
      <button
        className="trace-step__head"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className="trace-step__name">{step.name}</span>
        <span className="trace-step__status">{step.status}</span>
        {step.duration_ms != null && (
          <span className="trace-step__ms">{Math.round(step.duration_ms)} ms</span>
        )}
        <span className="trace-step__chevron">{expanded ? "▾" : "▸"}</span>
      </button>

      {expanded && step.detail && (
        isLlm ? (
          <LlmStepDetail detail={step.detail} />
        ) : (
          <pre className="trace-step__detail">
            {JSON.stringify(step.detail, null, 2)}
          </pre>
        )
      )}
    </div>
  );
}

// ─── Trace Panel ─────────────────────────────────────────────────────────────
export default function TracePanel({ collapsed, onToggle, trace, onDividerMouseDown }) {
  const steps = trace?.steps || [];

  return (
    <aside className={`tracepanel ${collapsed ? "tracepanel--collapsed" : ""}`}>
      {/* Drag divider — sits on the left edge of the panel, only shown when expanded */}
      {onDividerMouseDown && (
        <div
          className="tracepanel__divider"
          onMouseDown={onDividerMouseDown}
          role="separator"
          aria-orientation="vertical"
          title="Drag to resize"
        />
      )}

      <div className="tracepanel__header">
        <button
          className="tracepanel__toggle"
          onClick={onToggle}
          title={collapsed ? "Expand trace" : "Collapse trace"}
        >
          {collapsed ? "«" : "»"}
        </button>
        {!collapsed && <span className="tracepanel__title">Trace</span>}
      </div>

      {!collapsed && (
        <div className="tracepanel__body">
          {!trace && (
            <p className="tracepanel__empty">
              Run a query to see its execution trace.
            </p>
          )}

          {trace && (
            <>
              <div className="tracepanel__meta">
                <div>
                  <span className="tracepanel__k">trace_id</span>
                  <span className="tracepanel__v">{trace.trace_id}</span>
                </div>
                <div>
                  <span className="tracepanel__k">duration</span>
                  <span className="tracepanel__v">{trace.duration_ms} ms</span>
                </div>
                <div>
                  <span className="tracepanel__k">steps</span>
                  <span className="tracepanel__v">{steps.length}</span>
                </div>
              </div>

              <div className="tracepanel__steps">
                {steps.map((s, i) => (
                  <StepRow key={i} step={s} />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </aside>
  );
}
