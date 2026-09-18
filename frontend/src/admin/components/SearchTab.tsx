import { Search } from "lucide-react";
import { useState } from "react";
import { runSearch } from "../api";
import type { AdminDocument, SearchedArticle } from "../types";

interface Props {
  documents: AdminDocument[];
}

export function SearchTab({ documents }: Props) {
  const actNames = [
    ...new Set(
      documents.filter((d) => d.status !== "not_ingested").map((d) => d.short_name),
    ),
  ];
  const [q, setQ] = useState("");
  const [acts, setActs] = useState<string[]>([]);
  const [limit, setLimit] = useState(8);
  const [results, setResults] = useState<SearchedArticle[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (name: string) =>
    setActs((cur) => (cur.includes(name) ? cur.filter((a) => a !== name) : [...cur, name]));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResults((await runSearch(q.trim(), acts, limit)).articles);
    } catch {
      setError("поиск не удался — RAG-сервис доступен?");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <form className="search-bar" onSubmit={(e) => void submit(e)}>
        <input
          type="text"
          placeholder="Тестовый запрос к корпусу…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} aria-label="limit">
          {[5, 8, 15, 30].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
        <button className="btn-primary" type="submit" disabled={busy}>
          <Search size={14} /> Искать
        </button>
      </form>
      <div className="act-chips">
        {actNames.map((name) => (
          <button
            key={name}
            type="button"
            className={`act-chip ${acts.includes(name) ? "act-chip-on" : ""}`}
            onClick={() => toggle(name)}
          >
            {name}
          </button>
        ))}
      </div>
      {error && <p className="error-text">{error}</p>}
      {results !== null && results.length === 0 && (
        <p className="empty-state">Ничего не найдено</p>
      )}
      {results?.map((a) => (
        <div className="result-card" key={a.article_id}>
          <div className="result-head">
            <span>
              ст. {a.number} {a.act_short_name}
              {a.title ? ` — ${a.title}` : ""}
            </span>
            <span className="result-score">RRF {a.score.toFixed(4)}</span>
          </div>
          <details>
            <summary className="chunk-path">полный текст статьи</summary>
            <p className="article-text">{a.full_text}</p>
          </details>
          {a.matched_chunks.map((c) => (
            <div className="chunk-card" key={c.chunk_id}>
              <div className="chunk-path">
                {c.path} · score {c.score.toFixed(4)}
              </div>
              <div>{c.text}</div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
