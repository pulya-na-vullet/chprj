import { X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import type { Citation } from "../api/types";

export function ArticlePreview({
  articles,
  onClose,
  style,
}: {
  articles: Citation[];
  onClose: () => void;
  style?: React.CSSProperties;
}) {
  const single = articles.length === 1 ? articles[0] : null;
  const labelId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  return (
    <div
      className="article-preview"
      role="dialog"
      aria-modal="false"
      aria-labelledby={labelId}
      style={style}
    >
      <div className="article-preview-head">
        <span className="article-preview-ref" id={labelId}>
          {single ? `ст. ${single.number} ${single.act_short_name}` : "Источники"}
        </span>
        <button
          ref={closeRef}
          className="article-preview-close"
          onClick={onClose}
          aria-label="Закрыть"
        >
          <X size={16} />
        </button>
      </div>
      <div className="article-preview-body">
        {articles.map((a) => (
          <div key={`${a.act_short_name}-${a.number}`} className="article-preview-item">
            {!single && (
              <div className="article-preview-itemref">
                ст. {a.number} {a.act_short_name}
              </div>
            )}
            {a.title && <div className="article-preview-itemtitle">{a.title}</div>}
            <p>{a.full_text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
