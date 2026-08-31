import Sidebar from "./Sidebar.jsx";
import TracePanel from "./TracePanel.jsx";

// Three-pane shell. The center column is flexible and auto-resizes when either
// side pane collapses/expands (grid template columns are driven by CSS classes
// on the root element). TracePanel is only shown on the Chat view.

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
  const rootClass = [
    "layout",
    sidebarCollapsed ? "layout--sidebar-collapsed" : "",
    traceCollapsed || !showTrace ? "layout--trace-collapsed" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rootClass}>
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
        />
      ) : (
        // Placeholder cell so the grid doesn't collapse — hidden at collapsed width
        <div style={{ width: "var(--trace-w-collapsed)" }} />
      )}
    </div>
  );
}
