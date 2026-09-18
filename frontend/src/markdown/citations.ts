export interface CitationMatch {
  index: number; // start offset in the text
  length: number; // length of the matched substring
  raw: string; // the matched substring, e.g. "ст. 1477 ГК РФ"
  act: string; // matched short_name
  numbers: string[]; // ["1477", "1481"]
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Builds a regex matching "ст. <num>[, <num>...] <ACT>" where ACT is one of the
// known act short names (longest first so "КоАП РФ" wins over a shorter prefix).
function buildRegex(actNames: string[]): RegExp {
  const acts = [...actNames].sort((a, b) => b.length - a.length).map(escapeRegExp).join("|");
  const num = String.raw`\d+(?:[.\-]\d+)*`;
  return new RegExp(String.raw`ст\.\s*(${num}(?:\s*,\s*${num})*)\s+(${acts})`, "g");
}

export function findCitations(text: string, actNames: string[]): CitationMatch[] {
  if (actNames.length === 0) return [];
  const re = buildRegex(actNames);
  const out: CitationMatch[] = [];
  for (const m of text.matchAll(re)) {
    const numbers = m[1].split(",").map((n) => n.trim());
    out.push({
      index: m.index ?? 0,
      length: m[0].length,
      raw: m[0],
      act: m[2],
      numbers,
    });
  }
  return out;
}
