import { Database, FileText, Plus, Search as SearchIcon, Server } from "lucide-react";

export type AdminTab = "documents" | "search";

export interface HealthState {
  db: boolean;
  hnsw: boolean;
  gin: boolean;
}

interface Props {
  tab: AdminTab;
  onTab: (t: AdminTab) => void;
  health: HealthState | null;
  onUpload: () => void;
}

export function HeaderBar({ tab, onTab, health, onUpload }: Props) {
  return (
    <header className="topbar">
      <nav className="tabs">
        <button
          className={`tab ${tab === "documents" ? "tab-active" : ""}`}
          onClick={() => onTab("documents")}
        >
          <FileText size={14} /> Документы
        </button>
        <button
          className={`tab ${tab === "search" ? "tab-active" : ""}`}
          onClick={() => onTab("search")}
        >
          <SearchIcon size={14} /> Поиск
        </button>
      </nav>
      <div className="topbar-right">
        <span className="health" title="Состояние RAG-сервиса">
          <span className={`health-item ${health ? (health.db ? "health-ok" : "health-bad") : ""}`}>
            <Server size={13} /> БД
          </span>
          <span
            className={`health-item ${
              health ? (health.hnsw && health.gin ? "health-ok" : "health-bad") : ""
            }`}
          >
            <Database size={13} /> индексы
          </span>
        </span>
        <button className="btn-primary" onClick={onUpload}>
          <Plus size={15} /> Добавить документ
        </button>
      </div>
    </header>
  );
}
