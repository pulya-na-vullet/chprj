import { useEffect, useState } from "react";
import { listOpenRouterModels } from "../../api";
import type { AgentSettings, OpenRouterModel } from "../../types";
import { InfoIcon } from "./InfoIcon";

type Props = {
  value: AgentSettings;
  onChange: (next: AgentSettings) => void;
};

const REASONING = ["", "none", "minimal", "low", "medium", "high", "xhigh"];

// Synced with DEFAULT_REVIEW_MODEL in src/neurolegal/core/config.py — update together
// if the benchmark picks a new default.
const DEFAULT_REVIEW_MODEL_LABEL = "openai/gpt-4o-mini";

function fmtCtx(ctx: number | null | undefined): string {
  if (!ctx) return "—";
  if (ctx >= 1_000_000) return `${(ctx / 1_000_000).toFixed(ctx % 1_000_000 ? 1 : 0)}M`;
  if (ctx >= 1000) return `${Math.round(ctx / 1000)}K`;
  return String(ctx);
}

function perMillion(price: string | null | undefined): string {
  if (price == null) return "—";
  const n = Number(price) * 1_000_000;
  if (!Number.isFinite(n)) return "—";
  if (n === 0) return "$0";
  return `$${n.toFixed(n < 1 ? 2 : n < 100 ? 1 : 0)}`;
}

export function ModelSection({ value, onChange }: Props) {
  const [models, setModels] = useState<OpenRouterModel[]>([]);
  const [query, setQuery] = useState("");
  const [toolsOnly, setToolsOnly] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    void listOpenRouterModels()
      .then((r) => setModels(r.models))
      .catch(() => setModels([]));
  }, []);

  const g = value.generation ?? ({} as NonNullable<AgentSettings["generation"]>);
  const setGen = (patch: Partial<typeof g>) =>
    onChange({ ...value, generation: { ...g, ...patch } });

  const rv = value.review ?? ({} as NonNullable<AgentSettings["review"]>);
  const setReview = (patch: Partial<typeof rv>) =>
    onChange({ ...value, review: { ...rv, ...patch } });

  const q = query.toLowerCase();
  const filtered = models.filter(
    (m) =>
      (!toolsOnly || m.supports_tools) &&
      (m.id.toLowerCase().includes(q) || (m.name ?? "").toLowerCase().includes(q)),
  );
  const current = models.find((m) => m.id === value.model);

  return (
    <div>
      <div className="agent-card">
        <div className="agent-card-head">
          <span className="agent-card-title">Текущая модель</span>
          <InfoIcon text="Какая модель OpenRouter отвечает на запросы. Изменения применятся после перезапуска агента." />
        </div>
        <div className="model-hero">
          <div>
            <div className="model-hero-name">{current?.name ?? value.model}</div>
            <div className="model-hero-id">{value.model}</div>
          </div>
        </div>
        <div className="model-meta">
          <span className="meta-pill accent">{fmtCtx(current?.context_length)} контекст</span>
          <span className="meta-pill">{perMillion(current?.prompt_price)} / 1M вход</span>
          <span className="meta-pill">{perMillion(current?.completion_price)} / 1M выход</span>
          {current &&
            (current.supports_tools ? (
              <span className="meta-pill ok">tool-calling ✓</span>
            ) : (
              <span className="meta-pill">без tool-calling</span>
            ))}
        </div>
      </div>

      <div className="agent-card">
        <div className="agent-card-head">
          <span className="agent-card-title">Каталог OpenRouter</span>
          <InfoIcon text="Список доступных моделей с ценой и размером контекста. Кликните строку, чтобы выбрать модель." />
        </div>
        <div className="catalog-toolbar">
          <input
            className="agent-search"
            placeholder="поиск по названию или id…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            type="button"
            className={toolsOnly ? "act-chip act-chip-on" : "act-chip"}
            onClick={() => setToolsOnly((v) => !v)}
          >
            только с tool-calling
          </button>
        </div>
        <div className="catalog-scroll">
          {filtered.length === 0 ? (
            <div className="catalog-empty">
              {models.length === 0
                ? "каталог недоступен — проверьте OPENROUTER_API_KEY"
                : "ничего не найдено"}
            </div>
          ) : (
            <table className="catalog-table">
              <thead>
                <tr>
                  <th>Модель</th>
                  <th className="num">Контекст</th>
                  <th className="num">вход</th>
                  <th className="num">выход</th>
                  <th className="num">tools</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 200).map((m) => (
                  <tr
                    key={m.id}
                    className={m.id === value.model ? "selected" : ""}
                    onClick={() => onChange({ ...value, model: m.id })}
                  >
                    <td>
                      <div className="cat-name">{m.name}</div>
                      <div className="cat-id">{m.id}</div>
                    </td>
                    <td className="num">{fmtCtx(m.context_length)}</td>
                    <td className="num">{perMillion(m.prompt_price)}</td>
                    <td className="num">{perMillion(m.completion_price)}</td>
                    <td className="num">
                      <span className={m.supports_tools ? "cat-tools-yes" : "cat-tools-no"}>
                        {m.supports_tools ? "✓" : "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="agent-card">
        <div className="agent-card-head">
          <span className="agent-card-title">Параметры генерации</span>
        </div>
        <p className="agent-card-sub">
          Серым показано значение по умолчанию — оно действует, пока поле пустое.
        </p>
        <div className="agent-grid">
          <NumField label="Температура" def="1.0" tip="Насколько «творчески» отвечает модель. Ниже (0–0.3) — строго и предсказуемо, хорошо для юридических формулировок; выше — разнообразнее, но выше риск выдумок. По умолчанию 1.0." value={g.temperature ?? ""} step={0.1} onChange={(v) => setGen({ temperature: v })} />
          <NumField label="top_p" def="1.0" tip="Ограничивает выбор слов по суммарной вероятности. Альтернатива температуре — обычно меняют что-то одно. По умолчанию 1.0 (без ограничения)." value={g.top_p ?? ""} step={0.05} onChange={(v) => setGen({ top_p: v })} />
          <NumField label="Макс. токенов ответа" def="без лимита" tip="Верхний предел длины ответа. По умолчанию без явного лимита — модель сама решает." value={g.max_tokens ?? ""} step={1} onChange={(v) => setGen({ max_tokens: v })} />
          <NumField label="seed" def="случайный" tip="Фиксирует генерацию: один и тот же запрос даёт один и тот же ответ. По умолчанию случайный (ответы могут отличаться)." value={g.seed ?? ""} step={1} onChange={(v) => setGen({ seed: v })} />
          <div className="agent-field">
            <span className="agent-field-label">
              <code>reasoning_effort</code>
              <InfoIcon text="Сколько модель «думает» перед ответом (для reasoning-моделей). Больше усилий — выше качество и цена. По умолчанию — на усмотрение модели." />
            </span>
            <select
              className="agent-select"
              value={g.reasoning_effort ?? ""}
              onChange={(e) =>
                setGen({ reasoning_effort: (e.target.value || null) as typeof g.reasoning_effort })
              }
            >
              {REASONING.map((r) => (
                <option key={r} value={r}>
                  {r || "по умолчанию"}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button type="button" className="agent-disclosure" onClick={() => setShowAdvanced((v) => !v)}>
          {showAdvanced ? "▾" : "▸"} Расширенные параметры
        </button>
        {showAdvanced && (
          <>
            <hr className="agent-divider" />
            <div className="agent-grid">
              <NumField label="top_k" def="0 (выкл)" tip="Ограничивает выбор N самыми вероятными словами на каждом шаге. По умолчанию 0 — выключено." value={g.top_k ?? ""} step={1} onChange={(v) => setGen({ top_k: v })} />
              <NumField label="frequency_penalty" def="0" tip="Штраф за повтор уже встречавшихся слов. Выше — меньше повторов. По умолчанию 0." value={g.frequency_penalty ?? ""} step={0.1} onChange={(v) => setGen({ frequency_penalty: v })} />
              <NumField label="presence_penalty" def="0" tip="Штраф за использование уже упомянутых тем. Выше — больше новизны. По умолчанию 0." value={g.presence_penalty ?? ""} step={0.1} onChange={(v) => setGen({ presence_penalty: v })} />
            </div>
          </>
        )}
      </div>

      <div className="agent-card">
        <div className="agent-card-head">
          <span className="agent-card-title">Проверка договоров</span>
        </div>
        <p className="agent-card-sub">
          Модель и параллельность пайплайна проверки договоров (Review 2.0) — отдельные от модели
          чата выше. Пусто — переменная окружения <code>NEUROLEGAL_REVIEW_MODEL</code>, затем встроенный
          дефолт.
        </p>
        <div className="agent-grid">
          <div className="agent-field">
            <span className="agent-field-label">
              Модель проверки
              <InfoIcon text="Модель, которую использует пайплайн проверки договоров, — отдельная от модели чата выше. Пусто — переменная окружения NEUROLEGAL_REVIEW_MODEL, затем встроенный дефолт." />
            </span>
            <select
              className="agent-select"
              value={rv.model ?? ""}
              onChange={(e) => setReview({ model: e.target.value || null })}
            >
              <option value="">{`По умолчанию (${DEFAULT_REVIEW_MODEL_LABEL})`}</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>
          <NumField
            label="Параллельность"
            def="4"
            min={1}
            max={12}
            tip="Сколько правил пайплайна проверки договора проверяются одновременно. По умолчанию 4 (допустимо от 1 до 12)."
            value={rv.concurrency ?? ""}
            step={1}
            onChange={(v) => setReview({ concurrency: v })}
          />
        </div>
      </div>
    </div>
  );
}

function NumField({
  label,
  def,
  tip,
  value,
  step,
  min,
  max,
  onChange,
}: {
  label: string;
  def: string;
  tip: string;
  value: number | "";
  step: number;
  min?: number;
  max?: number;
  onChange: (v: number | null) => void;
}) {
  const mono = label === label.toLowerCase();
  return (
    <div className="agent-field">
      <span className="agent-field-label">
        {mono ? <code>{label}</code> : label}
        <InfoIcon text={tip} />
      </span>
      <input
        className="agent-input"
        type="number"
        step={step}
        min={min}
        max={max}
        placeholder={def}
        value={value}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
    </div>
  );
}
