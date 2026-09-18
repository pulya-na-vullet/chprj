import { RefreshCw, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { getArticle, listArticles } from "../api";
import type { AdminArticleDetail, AdminArticleListItem, AdminDocument } from "../types";
import { formatBytes, formatDate } from "../util";
import { ManifestForm } from "./ManifestForm";
import { StatusBadge } from "./StatusBadge";

type DrawerTab = "overview" | "articles" | "manifest";

const TAB_LABEL: Record<DrawerTab, string> = {
  overview: "Обзор",
  articles: "Статьи",
  manifest: "Манифест",
};

interface Props {
  doc: AdminDocument;
  jobRunning: boolean;
  onClose: () => void;
  onIngest: (doc: AdminDocument) => void;
  onDelete: (doc: AdminDocument) => void;
  onManifestSaved: () => void;
}

export function DocumentDrawer({
  doc,
  jobRunning,
  onClose,
  onIngest,
  onDelete,
  onManifestSaved,
}: Props) {
  const [tab, setTab] = useState<DrawerTab>("overview");
  const [articles, setArticles] = useState<AdminArticleListItem[] | null>(null);
  const [article, setArticle] = useState<AdminArticleDetail | null>(null);

  useEffect(() => {
    if (tab !== "articles" || articles !== null) return;
    const codeId = doc.code_id ?? doc.source_doc_id;
    void listArticles(codeId)
      .then((r) => setArticles(r.articles))
      .catch(() => setArticles([]));
  }, [tab, articles, doc]);

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <aside className="drawer">
        <div className="drawer-head">
          <div>
            <div className="drawer-title">{doc.short_name}</div>
            <div className="doc-fullname">{doc.full_name}</div>
          </div>
          <button className="btn-ghost" onClick={onClose} aria-label="Закрыть">
            <X size={16} />
          </button>
        </div>
        <div className="drawer-tabs">
          {(Object.keys(TAB_LABEL) as DrawerTab[]).map((t) => (
            <button
              key={t}
              className={`tab ${tab === t ? "tab-active" : ""}`}
              onClick={() => {
                setTab(t);
                setArticle(null);
              }}
            >
              {TAB_LABEL[t]}
            </button>
          ))}
        </div>
        <div className="drawer-body">
          {tab === "overview" && (
            <>
              <dl className="kv">
                <dt>Статус</dt>
                <dd>
                  <StatusBadge status={doc.status} />
                </dd>
                <dt>code_id</dt>
                <dd>{doc.code_id ?? "— (только в БД)"}</dd>
                <dt>Файл</dt>
                <dd>
                  {doc.file_path ?? "—"}
                  {doc.file_path && !doc.file_exists ? " (отсутствует!)" : ""}
                </dd>
                <dt>Размер</dt>
                <dd>{formatBytes(doc.file_size)}</dd>
                <dt>Изменён</dt>
                <dd>{formatDate(doc.file_mtime)}</dd>
                <dt>Статей</dt>
                <dd>{doc.articles_count ?? "—"}</dd>
                <dt>Чанков</dt>
                <dd>{doc.chunks_count ?? "—"}</dd>
                <dt>Дата загрузки</dt>
                <dd>{formatDate(doc.ingested_at)}</dd>
              </dl>
              <div className="drawer-actions">
                <button
                  className="btn-primary"
                  disabled={jobRunning || !doc.code_id || !doc.file_exists}
                  onClick={() => onIngest(doc)}
                >
                  <RefreshCw size={14} />
                  {doc.status === "not_ingested" ? "Загрузить" : "Переиндексировать"}
                </button>
                <button className="btn-ghost btn-danger" onClick={() => onDelete(doc)}>
                  <Trash2 size={14} /> Удалить
                </button>
              </div>
            </>
          )}
          {tab === "articles" &&
            (article ? (
              <div>
                <button className="btn-ghost" onClick={() => setArticle(null)}>
                  ← к списку
                </button>
                <h4>
                  ст. {article.number} {article.act_short_name}
                  {article.title ? ` — ${article.title}` : ""}
                </h4>
                <p className="article-text">{article.full_text}</p>
                <h4>Чанки ({article.chunks.length})</h4>
                {article.chunks.map((c) => (
                  <div className="chunk-card" key={c.chunk_id}>
                    <div className="chunk-path">{c.path}</div>
                    <div>{c.text}</div>
                  </div>
                ))}
              </div>
            ) : articles === null ? (
              <p className="empty-state">Загрузка…</p>
            ) : articles.length === 0 ? (
              <p className="empty-state">Статей нет — акт не загружен в БД</p>
            ) : (
              <ul className="article-list">
                {articles.map((a) => (
                  <li key={a.article_id} onClick={() => void getArticle(a.article_id).then(setArticle)}>
                    <span>
                      ст. {a.number}
                      {a.title ? ` — ${a.title}` : ""}
                    </span>
                    <span className="doc-fullname">{a.chunks_count}</span>
                  </li>
                ))}
              </ul>
            ))}
          {tab === "manifest" && <ManifestForm doc={doc} onSaved={onManifestSaved} />}
        </div>
      </aside>
    </>
  );
}
