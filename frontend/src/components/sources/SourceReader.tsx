import { ArrowUp, MessageCircle, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import * as api from "../../api/client";
import type { SourceArticleDetail, SourceArticleItem } from "../../api/types";
import { useChat } from "../../state/ChatContext";
import { IconButton } from "../../ui";
import { type ActGroup, partLabel } from "./filter";

const KIND_RU: Record<string, string> = {
  codex: "Кодекс",
  federal_law: "Федеральный закон",
  court: "Судебная практика",
};

const PANEL_CLOSE_MS = 240;

export function SourceReader({ group }: { group: ActGroup }) {
  const { askAboutAct } = useChat();
  const [partIdx, setPartIdx] = useState(0);
  const [articles, setArticles] = useState<SourceArticleItem[] | null>(null);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const [askMode, setAskMode] = useState(false);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState(false);
  const [openNum, setOpenNum] = useState<string | null>(null);
  const [panelShown, setPanelShown] = useState(false);
  const [details, setDetails] = useState<Record<string, SourceArticleDetail | "error">>({});
  const panelRef = useRef<HTMLElement>(null);
  const askInputRef = useRef<HTMLInputElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const part = group.parts[partIdx] ?? group.parts[0];
  const sdid = part.source_doc_id;

  useEffect(() => {
    let live = true;
    setArticles(null);
    setError(false);
    setOpenNum(null);
    setPanelShown(false);
    api
      .getSourceArticles(sdid)
      .then((a) => live && setArticles(a))
      .catch(() => live && setError(true));
    return () => {
      live = false;
    };
  }, [sdid]);

  const visible = useMemo(() => {
    if (!articles) return null;
    const q = query.trim().toLowerCase();
    if (!q) return articles;
    return articles.filter(
      (a) => a.number.toLowerCase().includes(q) || (a.title ?? "").toLowerCase().includes(q),
    );
  }, [articles, query]);

  const openArticle = visible?.find((a) => a.number === openNum) ?? null;
  const openId = openArticle ? String(openArticle.article_id) : null;
  const detail = openId ? details[openId] : undefined;

  // Текст статьи подгружается при открытии панели; неудача — явная ошибка
  // с повтором, а не вечная «Загрузка…».
  useEffect(() => {
    if (!openId || details[openId] !== undefined) return;
    let live = true;
    api
      .getArticleDetail(openId)
      .then((d) => live && setDetails((p) => ({ ...p, [openId]: d })))
      .catch(() => live && setDetails((p) => ({ ...p, [openId]: "error" })));
    return () => {
      live = false;
    };
  }, [openId, details]);

  // Панель монтируется закрытой и открывается следующим кадром — CSS-переход
  // отыгрывает слайд; закрытие ждёт анимацию перед размонтированием.
  useEffect(() => {
    if (!openNum) return;
    const raf = requestAnimationFrame(() => setPanelShown(true));
    return () => cancelAnimationFrame(raf);
  }, [openNum]);
  useEffect(
    () => () => {
      if (closeTimer.current) clearTimeout(closeTimer.current);
    },
    [],
  );

  const closePanel = () => {
    setPanelShown(false);
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => setOpenNum(null), PANEL_CLOSE_MS);
  };

  // Повторный клик по открытой строке закрывает панель; клик по другой строке
  // поверх идущего закрытия отменяет таймер.
  const togglePanel = (num: string) => {
    if (openNum === num && panelShown) {
      closePanel();
      return;
    }
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    setOpenNum(num);
    requestAnimationFrame(() => setPanelShown(true));
  };

  // Escape и клик за пределами панели закрывают её.
  useEffect(() => {
    if (!openNum) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closePanel();
    };
    const onDown = (e: MouseEvent) => {
      // клики по строкам оглавления сами управляют панелью (togglePanel)
      if ((e.target as Element).closest?.(".src-arow")) return;
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) closePanel();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
    // closePanel намеренно не в зависимостях: стабильный по содержимому
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openNum]);

  const enterAsk = () => {
    setAskMode(true);
    setAskError(false);
    requestAnimationFrame(() => askInputRef.current?.focus());
  };
  const exitAsk = () => {
    setAskMode(false);
    setQuestion("");
    setAskError(false);
  };

  const submitAsk = async () => {
    const text = question.trim();
    if (!text || asking) return;
    setAsking(true);
    setAskError(false);
    try {
      await askAboutAct(group.short, text);
    } catch {
      setAskError(true);
      setAsking(false);
      return;
    }
    setAsking(false);
    exitAsk();
  };

  const idx = openArticle && visible ? visible.indexOf(openArticle) : -1;
  const prev = idx > 0 && visible ? visible[idx - 1] : null;
  const next = idx >= 0 && visible && idx < visible.length - 1 ? visible[idx + 1] : null;

  return (
    <section className="src-rp">
      <div className="src-rhead">
        <div className="src-rtop">
          <span className="src-rname">{group.short}</span>
          <span className="src-rsp" />
          <button
            type="button"
            className="src-askbtn"
            onClick={() => (askMode ? exitAsk() : enterAsk())}
          >
            Спросить по акту
          </button>
        </div>
        <div className="src-rfull">{group.full}</div>
        <div className="src-rmeta">
          <span className="src-rkind">
            {[KIND_RU[group.kind] ?? group.kind, group.branch, articles && `${articles.length} статей`]
              .filter(Boolean)
              .join(" · ")}
          </span>
          {group.parts.length > 1 && (
            <div className="src-parts">
              {group.parts.map((p, i) => (
                <button
                  key={p.source_doc_id}
                  type="button"
                  className={i === partIdx ? "on" : ""}
                  onClick={() => setPartIdx(i)}
                >
                  {partLabel(p.full_name) ?? `ч. ${i + 1}`}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className={askMode ? "src-ask src-ask-on" : "src-ask"}>
        {askMode ? <MessageCircle size={15} /> : <Search size={15} />}
        <input
          ref={askInputRef}
          value={askMode ? question : query}
          placeholder={askMode ? `Спросить по ${group.short}…` : `Поиск по статьям ${group.short}…`}
          aria-label={askMode ? `Вопрос по ${group.short}` : `Поиск по статьям ${group.short}`}
          onChange={(e) => (askMode ? setQuestion(e.target.value) : setQuery(e.target.value))}
          onKeyDown={(e) => {
            if (!askMode) return;
            if (e.key === "Enter") void submitAsk();
            if (e.key === "Escape") exitAsk();
          }}
        />
        {askMode && (
          <IconButton
            className="send"
            view="primary"
            icon={<ArrowUp size={18} />}
            disabled={asking || !question.trim()}
            onClick={() => void submitAsk()}
            aria-label="Отправить вопрос"
          />
        )}
      </div>
      {askError && <div className="src-ask-note">Не удалось отправить вопрос. Попробуйте ещё раз.</div>}

      <div className="src-rscroll">
        <div className="src-thead">
          <span>Статья</span>
          <span>Название</span>
        </div>
        {error && <div className="src-note">Не удалось загрузить оглавление.</div>}
        {articles === null && !error && (
          <>
            <div className="src-skel" />
            <div className="src-skel" />
          </>
        )}
        {visible?.length === 0 && <div className="src-note">Ничего не найдено</div>}
        {visible?.map((a) => (
          <div
            key={String(a.article_id)}
            className={openNum === a.number ? "src-arow cur" : "src-arow"}
            role="button"
            tabIndex={0}
            onClick={() => togglePanel(a.number)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                togglePanel(a.number);
              }
            }}
          >
            <span className="src-an">ст. {a.number}</span>
            <span className="src-at">{a.title ?? ""}</span>
          </div>
        ))}
      </div>

      {openArticle && (
        <aside ref={panelRef} className={panelShown ? "src-panel src-panel-open" : "src-panel"}>
          <div className="src-ph">
            <span className="src-pname">
              ст. {openArticle.number} {group.short}
            </span>
            <button type="button" className="src-pclose" aria-label="Закрыть" onClick={closePanel}>
              »
            </button>
          </div>
          <div className="src-ptext">
            <div className="src-pkick">
              {[`Статья ${openArticle.number}`, group.short, partLabel(part.full_name)]
                .filter(Boolean)
                .join(" · ")}
            </div>
            <div className="src-ptitle">{openArticle.title ?? ""}</div>
            {detail === undefined && <div className="src-note">Загрузка…</div>}
            {detail === "error" && (
              <div className="src-note">
                Не удалось загрузить статью.{" "}
                <button
                  type="button"
                  className="src-retry"
                  onClick={() => openId && setDetails(({ [openId]: _drop, ...rest }) => rest)}
                >
                  Повторить
                </button>
              </div>
            )}
            {detail && detail !== "error" && (
              <>
                {detail.full_text
                  .split("\n")
                  .map((l) => l.trim())
                  .filter(Boolean)
                  .map((l, i) => (
                    <p key={i}>{l}</p>
                  ))}
                {(prev || next) && (
                  <div className="src-pn">
                    {prev ? (
                      <button type="button" onClick={() => togglePanel(prev.number)}>
                        <span className="k">← ст. {prev.number}</span>
                        <span className="v">{prev.title ?? ""}</span>
                      </button>
                    ) : (
                      <span className="src-pn-sp" />
                    )}
                    {next && (
                      <button type="button" className="next" onClick={() => togglePanel(next.number)}>
                        <span className="k">ст. {next.number} →</span>
                        <span className="v">{next.title ?? ""}</span>
                      </button>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </aside>
      )}
    </section>
  );
}
