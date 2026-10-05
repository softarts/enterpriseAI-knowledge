import { useState } from "react";

// Right pane: Verbose / Trace panel. Renders the REAL trace object returned by
// the backend for the most recent request — no mocked content. As the backend
// pipeline grows (retrieval, rerank, reflection...), new steps appear here
// automatically because we render whatever `steps` and sections the trace has.

// Pretty-print a payload that may already be a JSON string (the raw wire body
// arrives as text) or an object (everything reconstructed in Python).
function formatJson(value) {
  if (typeof value !== "string") {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value; // not JSON (plain text) — show as-is
  }
}

// Abbreviate a conversation id for display: "conversation-<uuid>" becomes
// "conversation-ae17acaa". The full id stays in the copy payload and in the
// title attribute so it can be recovered exactly.
function shortConversationId(id) {
  if (!id) return null;
  const text = String(id);
  const cut = text.lastIndexOf("-");
  return cut > 0 ? `${text.slice(0, cut)}-${text.slice(cut + 1, cut + 9)}` : text.slice(0, 16);
}

// ─── Raw output block with copy-to-clipboard ─────────────────────────────────
// Payloads are stored and sent in full (no backend truncation), so the block
// starts collapsed for anything substantial and expands in place — a long
// answer or a full tool result would otherwise bury the rest of the trace.
const RAW_PREVIEW_CHARS = 1200;

function RawOutput({ text, collapsible = true }) {
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(!collapsible);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const isLong = (text?.length || 0) > RAW_PREVIEW_CHARS;
  const canToggle = collapsible && isLong;
  const shown = canToggle && !expanded ? `${text.slice(0, RAW_PREVIEW_CHARS)}…` : text;

  return (
    <div className="trace-raw-output">
      <div className="trace-raw-output__header">
        <span className="trace-raw-output__label">
          Raw Output
          {isLong && (
            <span className="trace-raw-output__size">
              {text.length.toLocaleString()} chars
            </span>
          )}
        </span>
        <span className="trace-raw-output__actions">
          {canToggle && (
            <button
              type="button"
              className="trace-raw-output__toggle"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
            >
              {expanded ? "收起" : "展开全部"}
            </button>
          )}
          <button type="button" className="trace-raw-output__copy" onClick={handleCopy}>
            {copied ? "✓ Copied" : "Copy"}
          </button>
        </span>
      </div>
      <pre className="trace-raw-output__body">{shown}</pre>
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

// ─── HTTP call detail (LLM API request/response) ─────────────────────────────
// `kind: "http"` steps come from langchain_agent/app/call_trace.py's httpx
// event hooks: one entry per actual attempt, so a retried request shows up as
// its own request/response pair with an incrementing `attempt`.
// ─── HTTP call detail (one attempt to the LLM API) ───────────────────────────
// `kind: "http"` rows are the *transport* layer, from call_trace's httpx event
// hooks: one request/response pair per actual attempt, so a retry shows up as
// its own pair with a higher `attempt`. They sit underneath the `llm` row for
// the same call and answer "how many times did we hit the network, and with
// what status" — the `llm` row answers "what did the model say".
function HttpStepDetail({ detail }) {
  const entries = [
    ["method", detail.method],
    ["url", detail.url],
    ["attempt", detail.attempt],
    ["status_code", detail.status_code],
  ].filter(([, v]) => v !== undefined && v !== null);

  return (
    <div className="trace-step__sections">
      <div className="trace-section">
        <MetaTable entries={entries} />
      </div>
      {detail.headers && (
        <div className="trace-section">
          <div className="trace-section__title">Headers</div>
          <MetaTable entries={Object.entries(detail.headers)} />
        </div>
      )}
      {/* The real outbound wire payload, captured off httpx's replayable
          request body. This is the only place `stream` / `stream_options` and
          the exact tool schema are visible — the `llm` row's request summary
          is rebuilt from LangChain's view, not from the wire. */}
      {detail.body != null && (
        <div className="trace-section">
          <div className="trace-section__title">
            Request Body
            <span className="trace-section__hint">as sent on the wire</span>
          </div>
          <RawOutput text={formatJson(detail.body)} />
        </div>
      )}
    </div>
  );
}

// ─── kind pill (LLM / TOOL / HTTP / LOCAL) ───────────────────────────────────
function KindPill({ kind }) {
  if (!kind) return null;
  return <span className={`trace-step__kind trace-step__kind--${kind}`}>{kind}</span>;
}

// ─── Aggregated LLM call detail (call_trace `kind: "llm"`) ───────────────────
// One of these per LLM call, carrying the request that went out and the
// *merged* response that came back: langchain-core aggregates the SSE chunks
// before on_llm_end fires, so this is the whole answer for that call — not one
// token of it. Distinct from LlmStepDetail above, which renders the older
// top-level `llm` aggregate step returned by the non-streaming endpoint.
function LlmCallStepDetail({ detail }) {
  const request = detail?.request || {};
  const response = detail?.response;
  const meta = response?.response_metadata || {};
  // The model's *decision* to call a tool is recorded here, on the response of
  // the call that made it. The matching `tool` row further down is the
  // *execution* — one row each, not two rows per call. Call this out inline
  // because "a web_search row appeared but the llm_request body had no tools"
  // is the natural misreading.
  const decidedTools = response?.tool_calls || [];

  return (
    <div className="trace-step__sections">
      {request.node && (
        <div className="trace-section">
          <div className="trace-section__title">Graph Node</div>
          <MetaTable entries={[["node", request.node]]} />
        </div>
      )}

      {decidedTools.length > 0 && (
        <div className="trace-section trace-section--callout">
          <div className="trace-section__title">↳ This call requested a tool</div>
          <p className="trace-section__note">
            The model answered this call by asking for{" "}
            <strong>{decidedTools.map((c) => c.name).join(", ")}</strong>. The{" "}
            <code>tool</code> row further down is that tool actually executing —
            one row each, not two. Expand the matching{" "}
            <code>http_request</code> row to see the tool schema that was offered
            on the wire.
          </p>
        </div>
      )}

      {request.tools_bound?.length > 0 && (
        <div className="trace-section">
          <div className="trace-section__title">Tools Bound</div>
          <MetaTable
            entries={request.tools_bound.map((t) => [t.name, t.description || ""])}
          />
        </div>
      )}

      <div className="trace-section">
        <div className="trace-section__title">
          Request / Input
          <span className="trace-section__hint">
            {request.messages?.length || 0} messages
            {request.stream != null ? ` · stream=${request.stream}` : ""}
          </span>
        </div>
        <MetaTable
          entries={[
            ["model", request.model],
            ["messages", request.messages?.length],
          ].filter(([, v]) => v !== undefined && v !== null)}
        />
      </div>

      {response && (
        <div className="trace-section">
          <div className="trace-section__title">Aggregated Response</div>
          <MetaTable
            entries={[
              ["role", response.role],
              ["model_name", meta.model_name],
              ["finish_reason", meta.finish_reason],
              ["content_chars", response.content?.length],
              [
                "usage",
                response.usage
                  ? `in=${response.usage.input_tokens} out=${response.usage.output_tokens}`
                  : undefined,
              ],
            ].filter(([, v]) => v !== undefined && v !== null)}
          />
          {response.content ? <RawOutput text={response.content} /> : null}
          {response.tool_calls?.length > 0 && (
            <div className="trace-section">
              <div className="trace-section__title">Tool Calls</div>
              <MetaTable
                entries={response.tool_calls.map((c) => [
                  c.name,
                  JSON.stringify(c.args),
                ])}
              />
            </div>
          )}
        </div>
      )}

      {detail.error && (
        <div className="trace-section">
          <div className="trace-section__title">Error</div>
          <pre className="trace-step__detail">{detail.error}</pre>
        </div>
      )}
    </div>
  );
}

// ─── Generic step row (collapsible; structured for llm/http steps) ───────────
// ─── Tool execution detail (`kind: "tool"`) ─────────────────────────────────
// One row per *executed* tool call. The arguments are what the model asked
// for; the result is what the tool returned (for web_search that is the
// Tavily search output). Both are shown in full and collapse when long.
function ToolStepDetail({ detail }) {
  const [resultOpen, setResultOpen] = useState(false);
  const args = detail?.arguments;
  const result = detail?.result;
  const hasArgs = args && Object.keys(args).length > 0;

  return (
    <div className="trace-step__sections">
      {hasArgs && (
        <div className="trace-section">
          <div className="trace-section__title">
            Arguments (Input)
            <span className="trace-section__hint">requested by the model</span>
          </div>
          <RawOutput text={formatJson(args)} collapsible={false} />
        </div>
      )}
      {result != null && (
        <div className="trace-section">
          <button
            type="button"
            className="trace-section__collapsible"
            onClick={() => setResultOpen((v) => !v)}
            aria-expanded={resultOpen}
            style={{ width: "100%", background: "none", border: "none", cursor: "pointer", padding: 0, textAlign: "left" }}
          >
            <span className="trace-section__title">
              Result
              <span className="trace-section__hint">
                {resultOpen ? "click to hide" : "click to show"}
                {result.length ? ` · ${result.length.toLocaleString()} chars` : ""}
              </span>
            </span>
            <span className="trace-section__chevron">{resultOpen ? "▾" : "▸"}</span>
          </button>
          {resultOpen && (
            <>
              {/\.\.\.\[truncated\]/.test(result) && (
                <p className="trace-section__note">
                  This tool shortens its own output before handing it to the model
                  (a context-window budget, in <code>tool_layer.py</code>). The
                  trace shows the already-shortened text — i.e. exactly what the
                  model received.
                </p>
              )}
              <RawOutput text={result} />
            </>
          )}
        </div>
      )}
      {detail?.error && (
        <div className="trace-section">
          <div className="trace-section__title">Error</div>
          <pre className="trace-step__detail">{detail.error}</pre>
        </div>
      )}
      {!hasArgs && result == null && !detail?.error && (
        <div className="trace-section">
          <pre className="trace-step__detail">
            {JSON.stringify(detail ?? {}, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function StepRow({ step }) {
  const [expanded, setExpanded] = useState(true);
  const statusClass = `trace-step--${step.status || "ok"}`;
  const isLlmCall = step.kind === "llm";
  const isHttp = step.kind === "http";
  const isTool = step.kind === "tool";
  // The non-streaming endpoint's pre-existing top-level aggregate step.
  const isLlm = step.name === "llm";

  return (
    <div className={`trace-step ${statusClass}`}>
      <button
        className="trace-step__head"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <KindPill kind={step.kind} />
        <span className="trace-step__name">{step.name}</span>
        {/* Which conversation this row came from. Normally identical for every
            row of a turn; shown so a trace pasted from the log (where several
            conversations interleave) stays attributable. */}
        {step.conversation_id && (
          <span
            className="trace-step__conv"
            title={step.conversation_id}
            aria-label={`conversation ${step.conversation_id}`}
          >
            {shortConversationId(step.conversation_id)}
          </span>
        )}
        <span className="trace-step__status">{step.status}</span>
        {step.duration_ms != null && (
          <span className="trace-step__ms">{Math.round(step.duration_ms)} ms</span>
        )}
        <span className="trace-step__chevron">{expanded ? "▾" : "▸"}</span>
      </button>

      {expanded && step.detail && (
        isLlmCall ? (
          <LlmCallStepDetail detail={step.detail} />
        ) : isHttp ? (
          <HttpStepDetail detail={step.detail} />
        ) : isTool ? (
          <ToolStepDetail detail={step.detail} />
        ) : isLlm ? (
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

// ─── Archived trace (a finished conversation) ───────────────────────────────
// Collapsed by default: the payload is still all there, it just does not bury
// the trace you are currently looking at.
function ArchivedTrace({ entry }) {
  const [open, setOpen] = useState(false);
  const steps = entry.trace?.steps || [];

  return (
    <section className="trace-archived">
      <button
        type="button"
        className="trace-archived__head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title={entry.conversationId || undefined}
      >
        <span className="trace-archived__chevron">{open ? "▾" : "▸"}</span>
        <span className="trace-archived__label">Previous conversation</span>
        {entry.conversationId && (
          <span className="trace-archived__conv">
            {shortConversationId(entry.conversationId)}
          </span>
        )}
        <span className="trace-archived__count">{steps.length} steps</span>
      </button>
      {open && (
        <div className="trace-archived__body">
          {steps.map((s, i) => (
            <StepRow key={i} step={s} />
          ))}
        </div>
      )}
    </section>
  );
}

function RoundTraceItem({ entry }) {
  const [open, setOpen] = useState(false);
  const steps = entry.trace?.steps || [];
  const roundLabel = entry.round != null ? `Round ${entry.round}` : "Round";
  const questionPreview = entry.question
    ? ` · "${entry.question.slice(0, 24)}${entry.question.length > 24 ? "…" : ""}"`
    : "";

  return (
    <section className="trace-archived trace-round-archived" id={`trace-round-${entry.traceId}`}>
      <button
        type="button"
        className="trace-archived__head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title={entry.traceId ? `trace_id: ${entry.traceId}` : undefined}
      >
        <span className="trace-archived__chevron">{open ? "▾" : "▸"}</span>
        <span className="trace-archived__label">
          <strong>{roundLabel}</strong>
          {questionPreview}
        </span>
        {entry.traceId && (
          <span className="trace-archived__conv" title={`trace_id: ${entry.traceId}`}>
            {entry.traceId}
          </span>
        )}
        <span className="trace-archived__count">{steps.length} steps</span>
      </button>
      {open && (
        <div className="trace-archived__body">
          {entry.trace && (
            <div className="tracepanel__meta" style={{ padding: "4px 8px", marginBottom: "8px" }}>
              {entry.traceId && (
                <div>
                  <span className="tracepanel__k">trace_id</span>
                  <span className="tracepanel__v">{entry.traceId}</span>
                </div>
              )}
              {entry.trace.duration_ms != null && (
                <div>
                  <span className="tracepanel__k">duration</span>
                  <span className="tracepanel__v">{entry.trace.duration_ms} ms</span>
                </div>
              )}
              <div>
                <span className="tracepanel__k">steps</span>
                <span className="tracepanel__v">{steps.length}</span>
              </div>
            </div>
          )}
          {entry.question && (
            <section className="trace-turn" aria-label="Conversation turn question" style={{ marginBottom: "8px" }}>
              <div className="trace-turn__item">
                <div className="trace-turn__label">You</div>
                <pre className="trace-turn__text">{entry.question}</pre>
              </div>
            </section>
          )}
          {steps.map((s, i) => (
            <StepRow key={i} step={s} />
          ))}
        </div>
      )}
    </section>
  );
}

// ─── Trace Panel ─────────────────────────────────────────────────────────────
export default function TracePanel({
  collapsed,
  onToggle,
  trace,
  conversationId,
  roundTraces = [],
  archivedTraces = [],
  activeTraceOpen = true,
  onToggleActiveTrace,
  onDividerMouseDown,
}) {
  const steps = trace?.steps || [];
  const currentQuestion = trace?.request?.question;
  const currentAnswer = trace?.response?.answer;
  // Prefer the id carried on the rows themselves; fall back to the one the
  // caller knows (the streaming path only learns it once the first event
  // arrives, and the non-streaming trace object has no per-row id).
  const activeConversationId =
    steps.find((step) => step.conversation_id)?.conversation_id || conversationId;

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
        {!collapsed && (
          <span className="tracepanel__title">
            Trace
            {activeConversationId && (
              <span
                className="tracepanel__conv"
                title={`Conversation: ${activeConversationId}`}
              >
                {shortConversationId(activeConversationId)}
              </span>
            )}
          </span>
        )}
      </div>

      {!collapsed && (
        <div className="tracepanel__body">
          {!trace && roundTraces.length === 0 && (
            <p className="tracepanel__empty">
              Run a query to see its execution trace.
            </p>
          )}

          {/* Previous rounds in the current conversation, collapsed by default */}
          {roundTraces.length > 0 && (
            <div className="tracepanel__rounds">
              {roundTraces.map((entry) => (
                <RoundTraceItem key={entry.key || entry.traceId} entry={entry} />
              ))}
            </div>
          )}

          {trace && (
            <>
              {onToggleActiveTrace && steps.length > 0 && (
                <button
                  type="button"
                  className="tracepanel__current-toggle"
                  onClick={onToggleActiveTrace}
                  aria-expanded={activeTraceOpen}
                >
                  <span className="trace-archived__chevron">
                    {activeTraceOpen ? "▾" : "▸"}
                  </span>
                  Current turn {trace.round != null ? `(Round ${trace.round})` : ""}
                  <span className="trace-archived__count">
                    {steps.length} steps
                  </span>
                </button>
              )}

              <div
                className={`tracepanel__current ${activeTraceOpen ? "" : "tracepanel__current--collapsed"}`}
              >
              <div className="tracepanel__meta">
                {trace.trace_id != null && (
                  <div>
                    <span className="tracepanel__k">trace_id</span>
                    <span className="tracepanel__v">{trace.trace_id}</span>
                  </div>
                )}
                {trace.duration_ms != null && (
                  <div>
                    <span className="tracepanel__k">duration</span>
                    <span className="tracepanel__v">{trace.duration_ms} ms</span>
                  </div>
                )}
                <div>
                  <span className="tracepanel__k">steps</span>
                  <span className="tracepanel__v">{steps.length}</span>
                </div>
              </div>

              {(currentQuestion || currentAnswer) && (
                <section className="trace-turn" aria-label="Current conversation turn">
                  <div className="trace-turn__title">Current Turn</div>
                  {currentQuestion && (
                    <div className="trace-turn__item">
                      <div className="trace-turn__label">You</div>
                      <pre className="trace-turn__text">{currentQuestion}</pre>
                    </div>
                  )}
                  {currentAnswer && (
                    <div className="trace-turn__item">
                      <div className="trace-turn__label">Assistant</div>
                      <pre className="trace-turn__text">{currentAnswer}</pre>
                    </div>
                  )}
                </section>
              )}

              <div className="tracepanel__steps">
                  {steps.map((s, i) => (
                    <StepRow key={i} step={s} />
                  ))}
                </div>
              </div>
            </>
          )}

          {/* Traces from conversations the user has moved on from. Kept
              (collapsed) rather than discarded — they are usually why a new
              conversation was started, and they stay attributed to their own
              conversation id. */}
          {archivedTraces.map((entry) => (
            <ArchivedTrace key={entry.key} entry={entry} />
          ))}
        </div>
      )}
    </aside>
  );
}
