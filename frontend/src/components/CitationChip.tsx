import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArticlePreview } from "./ArticlePreview";
import { useCitations } from "./CitationsContext";

const PREVIEW_WIDTH = 360;
const MARGIN = 8;

export function CitationChip({
  dataAct,
  dataNumbers,
  children,
}: {
  dataAct?: string;
  dataNumbers?: string;
  children?: React.ReactNode;
}) {
  const citations = useCitations();
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const anchorRef = useRef<HTMLSpanElement>(null);
  const numbers = (dataNumbers ?? "").split(",").filter(Boolean);
  const matched = citations.filter(
    (c) => c.act_short_name === dataAct && numbers.includes(c.number),
  );
  const interactive = matched.length > 0;

  // While open: close on Escape, on a click outside, and on scrolling the page
  // (but NOT when scrolling inside the preview itself), plus on resize.
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        anchorRef.current?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest(".article-preview") || anchorRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onScroll = (e: Event) => {
      const t = e.target;
      // Scrolling within the preview body must not close it; page/chat scroll does.
      if (t instanceof Element && t.closest(".article-preview")) return;
      setOpen(false);
    };
    window.addEventListener("scroll", onScroll, true); // capture: also inner scroll containers
    window.addEventListener("resize", close);
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", close);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  // Position the fixed popup near the chip: flip above when there isn't enough
  // room below, and cap its height to the available space so it never overflows.
  let previewStyle: React.CSSProperties | undefined;
  if (rect) {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const left = Math.max(MARGIN, Math.min(rect.left, vw - PREVIEW_WIDTH - MARGIN));
    const below = vh - rect.bottom - MARGIN;
    const above = rect.top - MARGIN;
    const openUp = below < 260 && above > below;
    const maxHeight = Math.round(Math.min(0.6 * vh, Math.max(openUp ? above : below, 160)));
    previewStyle = openUp
      ? { left, bottom: vh - rect.top + 6, maxHeight }
      : { left, top: rect.bottom + 6, maxHeight };
  }

  const onActivate = () => {
    setRect(anchorRef.current?.getBoundingClientRect() ?? null);
    setOpen((v) => !v);
  };

  return (
    <span className="cite-wrap">
      <span
        ref={anchorRef}
        className={interactive ? "cite cite-interactive" : "cite"}
        onClick={interactive ? onActivate : undefined}
        onKeyDown={
          interactive
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onActivate();
                }
              }
            : undefined
        }
        role={interactive ? "button" : undefined}
        tabIndex={interactive ? 0 : undefined}
        aria-haspopup={interactive ? "dialog" : undefined}
        aria-expanded={interactive ? open : undefined}
      >
        {children}
      </span>
      {open &&
        interactive &&
        createPortal(
          <ArticlePreview
            articles={matched}
            onClose={() => {
              setOpen(false);
              anchorRef.current?.focus();
            }}
            style={previewStyle}
          />,
          document.body,
        )}
    </span>
  );
}
