// Right pane: Verbose / Trace panel. Renders the REAL trace object returned by
// the backend for the most recent request — no mocked content. As the backend
// pipeline grows (retrieval, rerank, agent...), new steps appear here
// automatically because we render whatever `steps` and sections the trace has.

function StepRow({ step }) {
  const statusClass = `trace-step--${step.status || "ok"}`;
  return (
    <div className={`trace-step ${statusClass}`}>
      <div className="trace-step__head">
        <span className="trace-step__name">{step.name}</span>
        <span className="trace-step__status">{step.status}</span>
        {step.duration_ms != null && (
          <span className="trace-step__ms">{step.duration_ms} ms</span>
        )}
      </div>
      {step.detail && (
        <pre className="trace-step__detail">
          {JSON.stringify(step.detail, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function TracePanel({ collapsed, onToggle, trace }) {
  const steps = trace?.steps || [];

  return (
    <aside className={`tracepanel ${collapsed ? "tracepanel--collapsed" : ""}`}>
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
