import type { ReviewListItem } from "../../api/types";

/** Поиск по своду прогонов: документ, плейбук, роль (спека E07 §2 —
 * «по документу/плейбуку»; роль — та же строка плейбука в таблице). */
export function filterReviews(items: ReviewListItem[], query: string): ReviewListItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  return items.filter((r) =>
    [r.document_filename ?? "", r.playbook_name, r.role ?? ""].some((s) =>
      s.toLowerCase().includes(q),
    ),
  );
}
