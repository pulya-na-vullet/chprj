import { Bot, Database, LayoutGrid, PanelLeft, PanelLeftClose, Users } from "lucide-react";
import { type ComponentType, useState } from "react";

export type AdminSection = "sources" | "agent" | "users" | "templates";

interface NavEntry {
  key: AdminSection;
  label: string;
  Icon: ComponentType<{ size?: number }>;
}

const NAV: NavEntry[] = [
  { key: "sources", label: "Источники", Icon: Database },
  { key: "agent", label: "Агент", Icon: Bot },
  { key: "users", label: "Пользователи", Icon: Users },
  { key: "templates", label: "Шаблоны", Icon: LayoutGrid },
];

interface Props {
  section: AdminSection;
  onSection: (s: AdminSection) => void;
}

export function AppSidebar({ section, onSection }: Props) {
  const [collapsed, setCollapsed] = useState(false);

  if (collapsed) {
    return (
      <aside className="sidebar sidebar-collapsed">
        <button
          className="sidebar-toggle"
          onClick={() => setCollapsed(false)}
          aria-label="Развернуть"
        >
          <PanelLeft size={18} />
        </button>
      </aside>
    );
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-card">
        <div className="sidebar-head">
          <span className="brand">Нейроюрист · админ</span>
          <button
            className="sidebar-toggle"
            onClick={() => setCollapsed(true)}
            aria-label="Свернуть"
          >
            <PanelLeftClose size={18} />
          </button>
        </div>
        <nav className="nav-list">
          {NAV.map(({ key, label, Icon }) => (
            <button
              key={key}
              className={`nav-item ${section === key ? "nav-item-active" : ""}`}
              onClick={() => onSection(key)}
            >
              <Icon size={16} /> {label}
            </button>
          ))}
        </nav>
      </div>
    </aside>
  );
}
