import { Play, RefreshCw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import type { AdminDocument } from "../types";
import { formatBytes, formatDate, formatNumber } from "../util";
import { StatusBadge } from "./StatusBadge";

const KIND_LABEL: Record<string, string> = { codex: "кодекс", federal_law: "ФЗ" };

interface Props {
  documents: AdminDocument[];
  totalChunks: number;
  dbSize: number;
  jobRunning: boolean;
  onSelect: (doc: AdminDocument) => void;
  onIngest: (doc: AdminDocument) => void;
  onDelete: (doc: AdminDocument) => void;
}

export function DocumentsTable({
  documents,
  totalChunks,
  dbSize,
  jobRunning,
  onSelect,
  onIngest,
  onDelete,
}: Props) {
  const [text, setText] = useState("");
  const [kind, setKind] = useState("all");
  const [status, setStatus] = useState("all");

  const filtered = useMemo(
    () =>
      documents.filter((d) => {
        const q = text.trim().toLowerCase();
        if (q && !`${d.short_name} ${d.full_name}`.toLowerCase().includes(q)) return false;
        if (kind !== "all" && d.kind !== kind) return false;
        if (status !== "all" && d.status !== status) return false;
        return true;
      }),
    [documents, text, kind, status],
  );

  return (
    <div>
      <div className="filters">
        <input
          placeholder="Фильтр по названию…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Тип">
          <option value="all">все типы</option>
          <option value="codex">кодексы</option>
          <option value="federal_law">ФЗ</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Статус">
          <option value="all">Все статусы</option>
          <option value="ingested">Загружен</option>
          <option value="not_ingested">Не загружен</option>
          <option value="stale">Файл новее БД</option>
          <option value="orphaned">Нет в манифесте</option>
        </select>
        <span className="filters-total">
          {documents.length} актов · {formatNumber(totalChunks)} чанков · {formatBytes(dbSize)}
        </span>
      </div>
      <table className="doc-table">
        <thead>
          <tr>
            <th>Акт</th>
            <th>Тип</th>
            <th>Статус</th>
            <th className="num">Статей</th>
            <th className="num">Чанков</th>
            <th>Дата загрузки</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((d) => (
            <tr
              key={d.code_id ?? d.source_doc_id}
              role="button"
              tabIndex={0}
              aria-label={`Открыть ${d.short_name}`}
              onClick={() => onSelect(d)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(d);
                }
              }}
            >
              <td>
                <span className="doc-name">{d.short_name}</span>{" "}
                <span className="doc-fullname">{d.full_name}</span>
              </td>
              <td>{KIND_LABEL[d.kind] ?? d.kind}</td>
              <td>
                <StatusBadge status={d.status} />
              </td>
              <td className="num">{formatNumber(d.articles_count)}</td>
              <td className="num">{formatNumber(d.chunks_count)}</td>
              <td>{formatDate(d.ingested_at)}</td>
              <td>
                <div className="row-actions">
                  <button
                    className="btn-ghost"
                    title={d.status === "not_ingested" ? "Загрузить" : "Переиндексировать"}
                    disabled={jobRunning || !d.code_id || !d.file_exists}
                    onClick={(e) => {
                      e.stopPropagation();
                      onIngest(d);
                    }}
                  >
                    {d.status === "not_ingested" ? <Play size={15} /> : <RefreshCw size={15} />}
                  </button>
                  <button
                    className="btn-ghost btn-danger"
                    title="Удалить"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(d);
                    }}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {filtered.length === 0 && <p className="empty-state">Ничего не найдено</p>}
    </div>
  );
}
