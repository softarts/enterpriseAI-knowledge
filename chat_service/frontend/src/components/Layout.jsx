import Sidebar from "./Sidebar.jsx";
import TracePanel from "./TracePanel.jsx";

// Three-pane shell. The center column is flexible and auto-resizes when either
// side pane collapses/expands (grid template columns are driven by CSS classes
// on the root element).

export default function Layout({
  sidebarCollapsed,
  onToggleSidebar,
  traceCollapsed,
  onToggleTrace,
  trace,
  children,
}) {
  const rootClass = [
    "layout",
    sidebarCollapsed ? "layout--sidebar-collapsed" : "",
    traceCollapsed ? "layout--trace-collapsed" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rootClass}>
      <Sidebar collapsed={sidebarCollapsed} onToggle={onToggleSidebar} />
      <main className="layout__center">{children}</main>
      <TracePanel
        collapsed={traceCollapsed}
        onToggle={onToggleTrace}
        trace={trace}
      />
    </div>
  );
}
