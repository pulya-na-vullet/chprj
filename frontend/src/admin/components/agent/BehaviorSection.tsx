import { useEffect, useState } from "react";
import { getAgentDefaults } from "../../api";
import type { AgentPromptDefaults, AgentSettings } from "../../types";
import { InfoIcon } from "./InfoIcon";

type Props = { value: AgentSettings; onChange: (next: AgentSettings) => void };

export function BehaviorSection({ value, onChange }: Props) {
  const [tab, setTab] = useState<"legal" | "text">("legal");
  const [defaults, setDefaults] = useState<AgentPromptDefaults | null>(null);
  const b = value.behavior;
  const setB = (patch: Partial<typeof b>) => onChange({ ...value, behavior: { ...b, ...patch } });

  useEffect(() => {
    void getAgentDefaults()
      .then(setDefaults)
      .catch(() => setDefaults(null));
  }, []);

  const promptKey = tab === "legal" ? "system_prompt_legal" : "system_prompt_text";
  const promptVal = (tab === "legal" ? b.system_prompt_legal : b.system_prompt_text) ?? "";
  const promptDefault = defaults ? defaults[promptKey] : "";
  const usingDefault = promptVal === "";

  return (
    <div>
      <div className="agent-card">
        <div className="agent-card-head">
          <span className="agent-card-title">Системные промпты</span>
          <InfoIcon text="Инструкция модели для двух режимов. legal — юридические вопросы (поиск + цитаты); text — работа с текстом без права. Пусто = встроенный дефолт." />
        </div>
        <div className="segmented">
          <button type="button" className={tab === "legal" ? "on" : ""} onClick={() => setTab("legal")}>
            Юридический
          </button>
          <button type="button" className={tab === "text" ? "on" : ""} onClick={() => setTab("text")}>
            Текстовый
          </button>
        </div>
        <p className="agent-card-sub" style={{ margin: "0 0 8px" }}>
          {usingDefault
            ? "Сейчас используется встроенный промпт по умолчанию (показан ниже серым). Начните печатать или нажмите «Редактировать из дефолта», чтобы переопределить."
            : "Используется ваш промпт. «Вернуть к дефолту» очистит поле и вернёт встроенный."}
        </p>
        <textarea
          className="agent-textarea"
          value={promptVal}
          placeholder={promptDefault || "(встроенный системный промпт)"}
          onChange={(e) => setB({ [promptKey]: e.target.value || null } as Partial<typeof b>)}
        />
        <div className="prompt-actions">
          {usingDefault ? (
            <button
              type="button"
              className="agent-disclosure"
              disabled={!promptDefault}
              onClick={() => setB({ [promptKey]: promptDefault } as Partial<typeof b>)}
            >
              ✎ Редактировать из дефолта
            </button>
          ) : (
            <button
              type="button"
              className="agent-disclosure"
              onClick={() => setB({ [promptKey]: null } as Partial<typeof b>)}
            >
              ↺ Вернуть к дефолту
            </button>
          )}
        </div>
      </div>

      <div className="agent-card">
        <div className="agent-card-head">
          <span className="agent-card-title">Цикл агента</span>
        </div>
        <div className="agent-grid">
          <div className="agent-field">
            <span className="agent-field-label">
              Макс. итераций инструментов
              <InfoIcon text="Сколько раз агент может вызвать инструменты за один ответ. На пределе — отказ «недостаточно оснований»." />
            </span>
            <input
              className="agent-input"
              type="number"
              min={1}
              max={10}
              value={b.max_tool_iterations ?? 4}
              onChange={(e) => setB({ max_tool_iterations: Number(e.target.value) })}
            />
          </div>
          <div className="agent-field">
            <span className="agent-field-label">
              <code>tool_choice</code>
              <InfoIcon text="Когда модель использует инструменты. auto — сама решает; required — обязана вызвать; none — запрещено (юр. вопросы тогда без поиска)." />
            </span>
            <select
              className="agent-select"
              value={b.tool_choice ?? "auto"}
              onChange={(e) => setB({ tool_choice: e.target.value as "auto" | "required" | "none" })}
            >
              <option value="auto">auto</option>
              <option value="required">required</option>
              <option value="none">none</option>
            </select>
          </div>
          <div className="agent-field">
            <span className="agent-field-label">
              Окно контекста (история)
              <InfoIcon text="Сколько прошлых сообщений диалога отправлять модели. Меньше — дешевле и быстрее, но агент «забывает» давнее. Пусто — вся история." />
            </span>
            <input
              className="agent-input"
              type="number"
              min={0}
              placeholder="вся история"
              value={b.history_window ?? ""}
              onChange={(e) =>
                setB({ history_window: e.target.value === "" ? null : Number(e.target.value) })
              }
            />
          </div>
        </div>
      </div>
    </div>
  );
}
