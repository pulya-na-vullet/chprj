import { Search } from "lucide-react";
import { useState } from "react";
import { ActTypeIcon } from "./ActTypeIcon";
import type { ActGroup } from "./filter";

const KIND_LABEL: Record<string, string> = {
  codex: "Кодексы",
  federal_law: "Федеральные законы",
  court: "Судебная практика",
};

export function SourceDocList({
  groups,
  query,
  onQuery,
  selected,
  onSelect,
}: {
  groups: ActGroup[];
  query: string;
  onQuery: (q: string) => void;
  selected: string | null;
  onSelect: (short: string) => void;
}) {
  // Свёрнутые группы; при активном поиске совпадения показываются поверх
  // свёрнутости, а после очистки строки группы возвращаются в своё состояние.
  const [closed, setClosed] = useState<ReadonlySet<string>>(new Set());
  const searching = query.trim().length > 0;

  const sections: { label: string; items: ActGroup[] }[] = [];
  for (const g of groups) {
    const label = KIND_LABEL[g.kind] ?? "Прочее";
    let sec = sections.at(-1);
    if (!sec || sec.label !== label) {
      sec = { label, items: [] };
      sections.push(sec);
    }
    sec.items.push(g);
  }

  const toggle = (label: string) => {
    setClosed((cur) => {
      const next = new Set(cur);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  return (
    <section className="src-lp">
      <div className="src-search">
        <Search size={14} />
        <input
          placeholder="Поиск по актам…"
          aria-label="Поиск по актам"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
        />
      </div>
      <div className="src-lpscroll">
        {groups.length === 0 && <div className="src-note">Ничего не найдено</div>}
        {sections.map((sec) => {
          const isClosed = !searching && closed.has(sec.label);
          return (
            <div key={sec.label} className={isClosed ? "src-grp src-grp-closed" : "src-grp"}>
              <button
                type="button"
                className="src-ghead"
                aria-expanded={!isClosed}
                onClick={() => toggle(sec.label)}
              >
                <span className="src-glabel">{sec.label}</span>
                <span className="src-gcount">{sec.items.length}</span>
                <span className="src-gsp" />
                <svg
                  className="src-gchev"
                  width="13"
                  height="13"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M8 10l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              <div className="src-gbody">
                <div>
                  {sec.items.map((g) => (
                    <button
                      key={g.short}
                      type="button"
                      className={selected === g.short ? "src-doc sel" : "src-doc"}
                      onClick={() => onSelect(g.short)}
                    >
                      <ActTypeIcon kind={g.kind} />
                      <span className="nm">{g.short}</span>
                      {g.parts.length > 1 && <span className="pt">{g.parts.length} ч.</span>}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
