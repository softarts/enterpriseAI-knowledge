// Left pane: collapsible navigation. Menu entries are placeholders for now
// (Chat is active; Documents/Settings are stubs for future stages).

const MENU = [
  { key: "chat", label: "Chat", icon: "💬", active: true },
  { key: "documents", label: "Documents", icon: "📄" },
  { key: "settings", label: "Settings", icon: "⚙️" },
];

export default function Sidebar({ collapsed, onToggle }) {
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
            className={`sidebar__item ${item.active ? "sidebar__item--active" : ""}`}
            title={item.label}
          >
            <span className="sidebar__icon">{item.icon}</span>
            {!collapsed && <span className="sidebar__label">{item.label}</span>}
          </button>
        ))}
      </nav>
    </aside>
  );
}
