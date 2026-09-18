import { BookOpen, Check, ChevronDown } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useChat } from "../state/ChatContext";
import { displayLabel } from "../state/sources";
import { Popover } from "../ui";
import { ActTypeIcon } from "./sources/ActTypeIcon";

export function SourceSelector() {
  const { state, setSelectedSources, retryActs } = useChat();
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const total = state.acts.length;
  const label = displayLabel(state.selectedSources, state.acts);

  // Группы каталога (E09, T-0057): выбор в селекторе идёт группами, не
  // отдельными актами. «Судебная практика» пока пуста — показывается
  // недоступной.
  const groups = useMemo(() => {
    const byKind = new Map<string, string[]>();
    for (const a of state.actsFull) {
      const arr = byKind.get(a.kind) ?? [];
      if (!arr.includes(a.short_name)) arr.push(a.short_name);
      byKind.set(a.kind, arr);
    }
    return [
      { kind: "codex", label: "Кодексы", shorts: byKind.get("codex") ?? [] },
      { kind: "federal_law", label: "Федеральные законы", shorts: byKind.get("federal_law") ?? [] },
      { kind: "court", label: "Судебная практика", shorts: byKind.get("court") ?? [] },
    ];
  }, [state.actsFull]);

  const groupChecked = (shorts: string[]) =>
    shorts.length > 0 && shorts.every((s) => state.selectedSources.includes(s));

  const toggleGroup = (shorts: string[]) => {
    if (shorts.length === 0) return;
    const next = groupChecked(shorts)
      ? state.selectedSources.filter((s) => !shorts.includes(s))
      : [...new Set([...state.selectedSources, ...shorts])];
    setSelectedSources(next);
  };

  // Бейдж пилюли считает выбранные группы, не акты (T-0059): «Все» при полном
  // (или пустом — фильтра нет) выборе, иначе число полностью выбранных групп.
  const badge =
    label === "Все" ? "Все" : String(groups.filter((g) => groupChecked(g.shorts)).length);

  // Панель живёт в портале, поэтому "клик вне" проверяет и пилюлю, и панель.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (anchor?.contains(t)) return;
      if (t instanceof Element && t.closest(".source-panel")) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open, anchor]);

  // preventDefault on mousedown keeps focus on the composer textarea, so opening
  // the menu and toggling sources never drops the active (glowing) edge.
  const keepFocus = (e: React.MouseEvent) => e.preventDefault();

  return (
    <div className="source-selector">
      <button
        type="button"
        ref={setAnchor}
        className="source-pill"
        data-tour="sources"
        disabled={total === 0 && state.actsStatus !== "error"}
        onMouseDown={keepFocus}
        onClick={() => setOpen((v) => !v)}
      >
        <BookOpen size={14} className="source-ico" /> Источники{" "}
        <span className="source-badge">{badge}</span> <ChevronDown size={14} />
      </button>
      <Popover anchorElement={anchor} open={open}>
        <div className="source-panel" onMouseDown={keepFocus}>
          <div className="source-panel-head">Источники законодательства</div>
          <div className="source-panel-list">
            {state.actsStatus === "loading" && (
              <div className="source-row source-row-status">Загружаю…</div>
            )}
            {state.actsStatus === "error" && (
              <div className="source-row source-row-status">
                <span>{state.actsError || "Не удалось загрузить источники"}</span>
                <button type="button" className="source-retry" onClick={() => void retryActs()}>
                  Повторить
                </button>
              </div>
            )}
            {state.actsStatus === "ready" &&
              groups.map((g) => (
                <button
                  key={g.kind}
                  type="button"
                  className={
                    groupChecked(g.shorts) ? "source-group source-group-on" : "source-group"
                  }
                  disabled={g.shorts.length === 0}
                  onClick={() => toggleGroup(g.shorts)}
                >
                  <ActTypeIcon kind={g.kind} />
                  {g.label}
                  <span className="source-group-mark" aria-hidden>
                    {groupChecked(g.shorts) && <Check size={11} strokeWidth={3} />}
                  </span>
                </button>
              ))}
          </div>
        </div>
      </Popover>
    </div>
  );
}
