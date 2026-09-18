import { useEffect, useMemo, useState } from "react";
import * as api from "../../api/client";
import type { Source } from "../../api/types";
import { collapseActs } from "./filter";
import { SourceDocList } from "./SourceDocList";
import { SourceReader } from "./SourceReader";

export function SourcesView() {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedShort, setSelectedShort] = useState<string | null>(null);

  const load = () => {
    setError(false);
    setSources(null);
    api.listSources().then(setSources).catch(() => setError(true));
  };
  useEffect(load, []);

  const allGroups = useMemo(() => (sources ? collapseActs(sources) : []), [sources]);

  useEffect(() => {
    if (allGroups.length && !selectedShort) {
      const gk = allGroups.find((g) => g.short === "ГК РФ");
      setSelectedShort((gk ?? allGroups[0]).short);
    }
  }, [allGroups, selectedShort]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? allGroups.filter((g) => `${g.short} ${g.full}`.toLowerCase().includes(q)) : allGroups;
  }, [allGroups, query]);

  const selected = allGroups.find((g) => g.short === selectedShort) ?? null;

  return (
    <main className="src">
      <div className="src-win">
        {error ? (
          <div className="src-state">
            Не удалось загрузить источники.
            <br />
            <button type="button" onClick={load}>
              Повторить
            </button>
          </div>
        ) : (
          <div className="src-body">
            <SourceDocList
              groups={visible}
              query={query}
              onQuery={setQuery}
              selected={selectedShort}
              onSelect={setSelectedShort}
            />
            {selected ? (
              <SourceReader key={selected.short} group={selected} />
            ) : (
              <section className="src-rp">
                <div className="src-state">Загрузка…</div>
              </section>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
