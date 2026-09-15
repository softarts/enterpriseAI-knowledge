import { useCallback, useEffect, useRef, useState } from "react";
import Sidebar from "./Sidebar.jsx";
import TracePanel from "./TracePanel.jsx";

// Three-pane shell. The center column is flexible and the trace column width
// is adjustable by dragging the divider (left edge of the TracePanel).

const TRACE_W_DEFAULT = 380;  // initial width, matches --trace-w
const TRACE_W_COLLAPSED = 44; // matches --trace-w-collapsed
const TRACE_MIN = 240;
const TRACE_MAX = 700;

export default function Layout({
  sidebarCollapsed,
  onToggleSidebar,
  traceCollapsed,
  onToggleTrace,
  trace,
  activeView,
  onViewChange,
  showTrace,
  children,
}) {
  const [traceWidth, setTraceWidth] = useState(TRACE_W_DEFAULT);
  const isDragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(traceWidth);

  const onDividerMouseDown = useCallback((e) => {
    e.preventDefault();
    isDragging.current = true;
    startX.current = e.clientX;
    startWidth.current = traceWidth;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [traceWidth]);

  useEffect(() => {
    const onMouseMove = (e) => {
      if (!isDragging.current) return;
      const delta = startX.current - e.clientX; // left drag = wider trace
      const next = Math.min(TRACE_MAX, Math.max(TRACE_MIN, startWidth.current + delta));
      setTraceWidth(next);
    };
    const onMouseUp = () => {
      if (!isDragging.current) return;
      isDragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  const effectiveTraceW = (!showTrace || traceCollapsed) ? TRACE_W_COLLAPSED : traceWidth;

  // Override grid-template-columns inline so the drag update is immediate
  // (no CSS transition fighting the drag). CSS transitions only kick in for
  // collapse/expand toggle which bypasses this because the divider is hidden.
  const rootStyle = {
    gridTemplateColumns: sidebarCollapsed
      ? `var(--sidebar-w-collapsed) 1fr ${effectiveTraceW}px`
      : `var(--sidebar-w) 1fr ${effectiveTraceW}px`,
  };

  const rootClass = [
    "layout",
    sidebarCollapsed ? "layout--sidebar-collapsed" : "",
    traceCollapsed || !showTrace ? "layout--trace-collapsed" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rootClass} style={rootStyle}>
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={onToggleSidebar}
        activeView={activeView}
        onViewChange={onViewChange}
      />
      <main className="layout__center">{children}</main>

      {showTrace ? (
        <TracePanel
          collapsed={traceCollapsed}
          onToggle={onToggleTrace}
          trace={trace}
          onDividerMouseDown={!traceCollapsed ? onDividerMouseDown : undefined}
        />
      ) : (
        // Placeholder cell so the grid doesn't collapse
        <div style={{ width: `${TRACE_W_COLLAPSED}px` }} />
      )}
    </div>
  );
}
