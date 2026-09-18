const STORAGE_KEY = "neurolegal.selectedSources";

export function toggleSource(selected: string[], shortName: string): string[] {
  return selected.includes(shortName)
    ? selected.filter((s) => s !== shortName)
    : [...selected, shortName];
}

// What to send as the chat request `acts`:
//   - empty selection → null (backend treats null as "search all acts")
//   - full selection  → null (no-op filter, same as empty)
//   - strict subset   → the subset
// The displayLabel() below matches this: 0 and full both show as "Все",
// never "0", so the UI never lies about an empty filter.
export function selectionToRequestActs(selected: string[], all: string[]): string[] | null {
  if (selected.length === 0) return null;
  if (selected.length === all.length) return null;
  return selected;
}

// What to render on the selector badge. Two semantically-equivalent inputs
// — empty selection and full selection — both display as "Все", matching
// what selectionToRequestActs sends to the backend (null = no filter).
export function displayLabel(selected: string[], all: string[]): string {
  if (selected.length === 0 || (all.length > 0 && selected.length === all.length)) {
    return "Все";
  }
  return String(selected.length);
}

export function loadSelected(): string[] | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as string[]) : null;
  } catch {
    return null;
  }
}

export function saveSelected(selected: string[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(selected));
  } catch {
    /* ignore quota/availability errors */
  }
}
