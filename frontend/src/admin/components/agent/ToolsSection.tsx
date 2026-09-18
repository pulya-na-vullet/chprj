import { useState } from "react";
import type { AgentSettings } from "../../types";
import { InfoIcon } from "./InfoIcon";
import { Switch } from "./Switch";

type Props = { value: AgentSettings; onChange: (next: AgentSettings) => void };

export function ToolsSection({ value, onChange }: Props) {
  const [openCards, setOpenCards] = useState<Record<string, boolean>>({
    rag_search: true,
    web_search: false,
    web_fetch: false,
  });

  const t = value.tools;
  const setTool = <K extends keyof typeof t>(key: K, patch: Partial<(typeof t)[K]>) =>
    onChange({ ...value, tools: { ...t, [key]: { ...t[key], ...patch } } });

  const toggleCard = (key: string) =>
    setOpenCards((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <>
      {/* rag_search */}
      <div className="agent-card">
        <div className="tool-head">
          <Switch
            checked={t.rag_search.enabled}
            onChange={(v) => setTool("rag_search", { enabled: v })}
            label="rag_search"
          />
          <div className="tool-name">
            <div className="title">
              <code>rag_search</code>
              <span className="tag-builtin">встроенная</span>
              <InfoIcon text="Поиск по корпусу законов. Если выключить — агент не сможет искать статьи и на юридические вопросы будет отвечать отказом." />
            </div>
            <div className="desc">Гибридный поиск релевантных статей в корпусе законодательства РФ</div>
          </div>
          <button
            type="button"
            className="agent-disclosure"
            style={{ marginTop: 0 }}
            onClick={() => toggleCard("rag_search")}
          >
            {openCards.rag_search ? "▾" : "▸"}
          </button>
        </div>
        {openCards.rag_search && (
          <div className="tool-body">
            <div className="agent-grid">
              <div className="agent-field">
                <span className="agent-field-label">
                  Лимит результатов
                  <InfoIcon text="Сколько статей возвращать на один поиск. Больше — шире контекст, но дороже." />
                </span>
                <input
                  className="agent-input"
                  type="number"
                  min={1}
                  max={50}
                  value={t.rag_search.limit ?? 8}
                  onChange={(e) => setTool("rag_search", { limit: Number(e.target.value) })}
                />
              </div>
              <div className="agent-field">
                <span className="agent-field-label">
                  Порог релевантности
                  <InfoIcon text="Отсекает слабые совпадения. 0 — выключено (учитываются все найденные статьи). Выше — на запросы не по корпусу агент отвечает «нет оснований»." />
                </span>
                <input
                  className="agent-input"
                  type="number"
                  min={0}
                  step={0.01}
                  value={t.rag_search.min_score ?? 0}
                  onChange={(e) => setTool("rag_search", { min_score: Number(e.target.value) })}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* fetch_article */}
      <div className="agent-card">
        <div className="tool-head">
          <Switch
            checked={t.fetch_article.enabled}
            onChange={(v) => setTool("fetch_article", { enabled: v })}
            label="fetch_article"
          />
          <div className="tool-name">
            <div className="title">
              <code>fetch_article</code>
              <span className="tag-builtin">встроенная</span>
              <InfoIcon text="Точное получение статьи по акту и номеру." />
            </div>
            <div className="desc">Точное получение статьи по акту и номеру</div>
          </div>
        </div>
      </div>

      {/* list_acts */}
      <div className="agent-card">
        <div className="tool-head">
          <Switch
            checked={t.list_acts.enabled}
            onChange={(v) => setTool("list_acts", { enabled: v })}
            label="list_acts"
          />
          <div className="tool-name">
            <div className="title">
              <code>list_acts</code>
              <span className="tag-builtin">встроенная</span>
              <InfoIcon text="Список доступных актов в корпусе законодательства." />
            </div>
            <div className="desc">Список доступных актов в корпусе</div>
          </div>
        </div>
      </div>

      {/* date_calculator */}
      <div className="agent-card">
        <div className="tool-head">
          <Switch
            checked={t.date_calculator.enabled}
            onChange={(v) => setTool("date_calculator", { enabled: v })}
            label="date_calculator"
          />
          <div className="tool-name">
            <div className="title">
              <code>date_calculator</code>
              <span className="tag-builtin">встроенная</span>
              <InfoIcon text="Расчёт сроков и дат, включая рабочие дни РФ." />
            </div>
            <div className="desc">Расчёт сроков и дат, включая рабочие дни РФ</div>
          </div>
        </div>
      </div>

      {/* web_search */}
      <div className="agent-card">
        <div className="tool-head">
          <Switch
            checked={t.web_search.enabled}
            onChange={(v) => setTool("web_search", { enabled: v })}
            label="web_search"
          />
          <div className="tool-name">
            <div className="title">
              <code>web_search</code>
              <InfoIcon text="Результаты — контекст, не правовое основание; нужен NEUROLEGAL_TAVILY_API_KEY." />
            </div>
            <div className="desc">Поиск в интернете (контекст, не основание для нормы). Требует ключ Tavily</div>
          </div>
          <button
            type="button"
            className="agent-disclosure"
            style={{ marginTop: 0 }}
            onClick={() => toggleCard("web_search")}
          >
            {openCards.web_search ? "▾" : "▸"}
          </button>
        </div>
        {openCards.web_search && (
          <div className="tool-body">
            <div className="agent-grid">
              <div className="agent-field">
                <span className="agent-field-label">
                  Макс. результатов
                  <InfoIcon text="Сколько результатов возвращать на один веб-поиск (1–20)." />
                </span>
                <input
                  className="agent-input"
                  type="number"
                  min={1}
                  max={20}
                  value={t.web_search.max_results ?? 5}
                  onChange={(e) => setTool("web_search", { max_results: Number(e.target.value) })}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* web_fetch */}
      <div className="agent-card">
        <div className="tool-head">
          <Switch
            checked={t.web_fetch.enabled}
            onChange={(v) => setTool("web_fetch", { enabled: v })}
            label="web_fetch"
          />
          <div className="tool-name">
            <div className="title">
              <code>web_fetch</code>
              <InfoIcon text="Загружает страницу по URL. Результат — контекст, не правовое основание." />
            </div>
            <div className="desc">Загрузка страницы по URL (контекст, не основание)</div>
          </div>
          <button
            type="button"
            className="agent-disclosure"
            style={{ marginTop: 0 }}
            onClick={() => toggleCard("web_fetch")}
          >
            {openCards.web_fetch ? "▾" : "▸"}
          </button>
        </div>
        {openCards.web_fetch && (
          <div className="tool-body">
            <div className="agent-grid">
              <div className="agent-field">
                <span className="agent-field-label">
                  Макс. символов
                  <InfoIcon text="Сколько символов текста страницы передавать агенту (1000–100000)." />
                </span>
                <input
                  className="agent-input"
                  type="number"
                  min={1000}
                  max={100000}
                  step={1000}
                  value={t.web_fetch.max_chars ?? 20000}
                  onChange={(e) => setTool("web_fetch", { max_chars: Number(e.target.value) })}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
