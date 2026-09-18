import type { TemplateDraftData } from "../../api/types";
import { pluralRu } from "../../util/format";

const SOURCE_LABEL: Record<string, string> = {
  profile: "из профиля",
  document: "из документа",
  user: "уточнили",
};

/** Панель сводки staged-черновика (E20, flow-full шаг 6): что пользователь
 * видит здесь, то ровно и уйдёт в рендер после подтверждения. Живёт и в
 * стриме (draftTemplateDraft), и на сообщении (message.template_draft) —
 * переживает перезагрузку истории тем же приёмом, что review-карточка. */
export function TemplateDraftCard({ data }: { data: TemplateDraftData }) {
  const count = data.fields.length;
  return (
    <section className="tpld" aria-label={`Черновик: ${data.template.title}`}>
      <div className="tpld-head">
        <b>{data.template.title}</b>
        <span>
          {count} {pluralRu(count, ["поле", "поля", "полей"])}
        </span>
      </div>
      {data.fields.map((f) => (
        <div key={f.name} className="tpld-row">
          <span className="tpld-k">{f.label}</span>
          <span className="tpld-v">
            {f.value || "—"}
            <span className="tpld-src">{SOURCE_LABEL[f.source] ?? f.source}</span>
          </span>
        </div>
      ))}
    </section>
  );
}
