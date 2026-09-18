import { ArrowRight, FileText } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { listTemplates } from "../../api/client";
import type { TemplateSummary } from "../../api/types";
import { useChat } from "../../state/ChatContext";
import { pluralRu } from "../../util/format";

function fieldsLabel(count: number): string {
  return `${count} ${pluralRu(count, ["поле", "поля", "полей"])}`;
}

/** Категории в порядке появления — сервис отдаёт список, отсортированный
 * по категории и названию, порядок сохраняем как есть. */
function groupByCategory(templates: TemplateSummary[]): [string, TemplateSummary[]][] {
  const groups = new Map<string, TemplateSummary[]>();
  for (const t of templates) {
    const list = groups.get(t.category) ?? [];
    list.push(t);
    groups.set(t.category, list);
  }
  return [...groups.entries()];
}

export function TemplatesView() {
  const { startTemplate } = useChat();
  const [templates, setTemplates] = useState<TemplateSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setTemplates(await listTemplates());
    } catch {
      setError("Не удалось загрузить шаблоны. Попробуйте обновить.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="templates">
      <div className="templates-win">
        <div className="templates-head">
          <h2 className="templates-title">Шаблоны</h2>
          <p className="templates-sub">
            Готовые документы — выберите, остальное заполним вместе в чате
          </p>
        </div>
        <div className="templates-body">
          {error ? (
            <div className="templates-error" role="alert">
              <span>{error}</span>
              <button type="button" className="files-btn" onClick={() => void load()}>
                Обновить
              </button>
            </div>
          ) : templates === null ? (
            <div className="templates-grid" aria-hidden="true">
              {Array.from({ length: 6 }, (_, i) => (
                <div key={i} className="templates-skel" />
              ))}
            </div>
          ) : templates.length === 0 ? (
            <p className="templates-empty">Шаблоны скоро появятся</p>
          ) : (
            groupByCategory(templates).map(([category, items]) => (
              <section key={category}>
                <div className="templates-cat">{category}</div>
                <div className="templates-grid">
                  {items.map((t) => (
                    <button
                      key={t.slug}
                      type="button"
                      className="templates-card"
                      onClick={() => startTemplate(t.slug, t.title)}
                    >
                      <FileText size={20} strokeWidth={1.75} />
                      <b>{t.title}</b>
                      <p>{t.description}</p>
                      <span className="templates-meta">{fieldsLabel(t.field_count)}</span>
                      <span className="templates-go">
                        Заполнить <ArrowRight size={14} />
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
