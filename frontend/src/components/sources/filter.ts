import type { Source } from "../../api/types";

// "(часть первая)" → "ч. 1" — disambiguates multi-part codices (ГК/НК).
const PART_STEMS: [string, string][] = [
  ["перв", "1"],
  ["втор", "2"],
  ["трет", "3"],
  ["четверт", "4"],
  ["пят", "5"],
];

export function partLabel(fullName: string): string | null {
  const m = fullName.match(/\(часть\s+([^)\s]+)/i);
  if (!m) return null;
  const stem = m[1].toLowerCase();
  for (const [k, v] of PART_STEMS) if (stem.startsWith(k)) return `ч. ${v}`;
  return null;
}

export function baseFullName(fullName: string): string {
  return fullName.replace(/\s*\(часть[^)]*\)\s*/i, " ").trim();
}

function partNum(fullName: string): number {
  const p = partLabel(fullName);
  return p ? Number.parseInt(p.replace(/\D/g, ""), 10) : 0;
}

// One entry per act, collapsing multi-part codices (ГК/НК) into a single act
// with its ordered parts. Codices first, then federal laws, alphabetical within.
export interface ActGroup {
  short: string;
  full: string;
  kind: string;
  branch: string | null;
  parts: Source[];
}

export function collapseActs(sources: Source[]): ActGroup[] {
  const by = new Map<string, Source[]>();
  for (const s of sources) {
    const arr = by.get(s.short_name) ?? [];
    arr.push(s);
    by.set(s.short_name, arr);
  }
  const groups: ActGroup[] = [];
  by.forEach((parts, short) => {
    parts.sort((a, b) => partNum(a.full_name) - partNum(b.full_name) || a.full_name.localeCompare(b.full_name, "ru"));
    const p0 = parts[0];
    groups.push({ short, full: baseFullName(p0.full_name), kind: p0.kind, branch: p0.branch, parts });
  });
  const ord: Record<string, number> = { codex: 0, federal_law: 1 };
  groups.sort((a, b) => (ord[a.kind] ?? 9) - (ord[b.kind] ?? 9) || a.short.localeCompare(b.short, "ru"));
  return groups;
}
