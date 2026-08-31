// Left pane: collapsible navigation with Chat / Documents (Import) / Settings.

const MENU = [
  { key: "chat", label: "Chat", icon: "💬" },
  { key: "import", label: "文档导入", icon: "📥" },
];

export default function Sidebar({ collapsed, onToggle, activeView, onViewChange }) {
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
      </nav>
    </aside>
  );
}
