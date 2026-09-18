import { useEffect, useState } from "react";
import { getAgentSettings, saveAgentSettings } from "../api";
import type { AgentSettings } from "../types";
import { BehaviorSection } from "./agent/BehaviorSection";
import { McpSection } from "./agent/McpSection";
import { ModelSection } from "./agent/ModelSection";
import { SaveBar } from "./agent/SaveBar";
import { SkillsSection } from "./agent/SkillsSection";
import { ToolsSection } from "./agent/ToolsSection";

type Tab = "model" | "behavior" | "tools" | "mcp" | "skills";

const NAV: { id: Tab; label: string; soon?: boolean }[] = [
  { id: "model", label: "Модель" },
  { id: "behavior", label: "Поведение" },
  { id: "tools", label: "Тулзы" },
  { id: "mcp", label: "MCP", soon: true },
  { id: "skills", label: "Скиллы", soon: true },
];

const HEAD: Record<Tab, { title: string; sub: string }> = {
  model: { title: "Модель", sub: "Выбор модели OpenRouter и параметры генерации" },
  behavior: { title: "Поведение", sub: "Системные промпты и параметры цикла агента" },
  tools: { title: "Тулзы", sub: "Инструменты, доступные агенту, и их настройки" },
  mcp: { title: "MCP", sub: "Внешние инструменты по протоколу MCP" },
  skills: { title: "Скиллы", sub: "Готовые навыки — связки промпта и тулзов" },
};

export function AgentTab() {
  const [tab, setTab] = useState<Tab>("model");
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedBanner, setSavedBanner] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getAgentSettings()
      .then(setSettings)
      .catch(() => setError("не удалось загрузить настройки агента — RAG-сервис доступен?"));
  }, []);

  const update = (next: AgentSettings) => {
    setSettings(next);
    setDirty(true);
    setSavedBanner(false);
  };

  const save = async () => {
    if (!settings) return;
    const snapshot = settings;
    setSaving(true);
    setError(null);
    try {
      await saveAgentSettings(snapshot);
      setSettings((cur) => {
        if (cur === snapshot) setDirty(false);
        return cur;
      });
      setSavedBanner(true);
    } catch (e) {
      setError(`не удалось сохранить: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  if (error && !settings) {
    return (
      <div className="agent-placeholder">
        <p>{error}</p>
      </div>
    );
  }
  if (!settings) {
    return (
      <div className="agent-placeholder">
        <p>Загрузка…</p>
      </div>
    );
  }

  const editable = tab === "model" || tab === "behavior" || tab === "tools";

  return (
    <div className="agent-shell">
      <nav className="agent-subnav">
        {NAV.map((n) => (
          <button
            key={n.id}
            className={tab === n.id ? "active" : ""}
            onClick={() => setTab(n.id)}
          >
            {n.label}
            {n.soon && <span className="soon-pill">скоро</span>}
          </button>
        ))}
      </nav>
      <div className="agent-content">
        <div className="agent-content-inner">
          <div className="agent-head">
            <h2>{HEAD[tab].title}</h2>
            <p>{HEAD[tab].sub}</p>
          </div>
          {error && <p className="error-text">{error}</p>}
          {tab === "model" && <ModelSection value={settings} onChange={update} />}
          {tab === "behavior" && <BehaviorSection value={settings} onChange={update} />}
          {tab === "tools" && <ToolsSection value={settings} onChange={update} />}
          {tab === "mcp" && <McpSection />}
          {tab === "skills" && <SkillsSection />}
          {editable && (
            <SaveBar dirty={dirty} saving={saving} savedBanner={savedBanner} onSave={() => void save()} />
          )}
        </div>
      </div>
    </div>
  );
}
