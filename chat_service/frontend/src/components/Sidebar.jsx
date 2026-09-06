// Left pane: collapsible navigation with a grouped Documents menu.

const MENU = [
  { key: "chat", label: "Chat", icon: "💬" },
];

const DOCUMENT_ITEMS = [
  { key: "import", label: "Import", icon: "📥" },
  { key: "browse", label: "Browse", icon: "🗂️" },
];

export default function Sidebar({ collapsed, onToggle, activeView, onViewChange }) {
  const documentsActive = DOCUMENT_ITEMS.some((item) => item.key === activeView);

  return (
    <aside className={`sidebar ${collapsed ? "sidebar--collapsed" : ""}`}>
      <div className="sidebar__header">
        {!collapsed && <span className="sidebar__title">Playground</span>}
        <button
          className="sidebar__toggle"
          onClick={onToggle}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? "»" : "«"}
        </button>
      </div>

      <nav className="sidebar__nav">
        {MENU.map((item) => (
          <button
            key={item.key}
            className={`sidebar__item ${activeView === item.key ? "sidebar__item--active" : ""}`}
            title={item.label}
            onClick={() => onViewChange?.(item.key)}
            id={`nav-${item.key}`}
          >
            <span className="sidebar__icon">{item.icon}</span>
            {!collapsed && <span className="sidebar__label">{item.label}</span>}
          </button>
        ))}
        <div className={`sidebar__group ${documentsActive ? "sidebar__group--active" : ""}`}>
          <div className="sidebar__group-title" title="Documents">
            <span className="sidebar__icon">📄</span>
            {!collapsed && <span className="sidebar__label">Documents</span>}
            {!collapsed && <span className="sidebar__group-chevron">⌄</span>}
          </div>
          {!collapsed && (
            <div className="sidebar__submenu">
              {DOCUMENT_ITEMS.map((item) => (
                <button
                  key={item.key}
                  className={`sidebar__item sidebar__item--sub ${activeView === item.key ? "sidebar__item--active" : ""}`}
                  onClick={() => onViewChange?.(item.key)}
                  id={`nav-${item.key}`}
                >
                  <span className="sidebar__icon">{item.icon}</span>
                  <span className="sidebar__label">{item.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </nav>
    </aside>
  );
}
