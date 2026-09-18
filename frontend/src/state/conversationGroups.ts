import type { Conversation } from "../api/types";

export interface ConvGroup {
  label: string;
  items: Conversation[];
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

// Groups conversations (already sorted newest-first by the backend) into
// Сегодня / Вчера / Ранее by `updated_at`. Unparseable dates fall into Ранее.
// Empty groups are omitted so the sidebar never shows a bare header.
export function groupConversationsByTime(convs: Conversation[], now: Date): ConvGroup[] {
  const today = startOfDay(now);
  const yesterday = today - 86_400_000;
  const todayItems: Conversation[] = [];
  const yesterdayItems: Conversation[] = [];
  const olderItems: Conversation[] = [];

  for (const c of convs) {
    const t = Date.parse(c.updated_at);
    if (Number.isFinite(t) && t >= today) todayItems.push(c);
    else if (Number.isFinite(t) && t >= yesterday) yesterdayItems.push(c);
    else olderItems.push(c);
  }

  const out: ConvGroup[] = [];
  if (todayItems.length) out.push({ label: "Сегодня", items: todayItems });
  if (yesterdayItems.length) out.push({ label: "Вчера", items: yesterdayItems });
  if (olderItems.length) out.push({ label: "Ранее", items: olderItems });
  return out;
}
