const STORAGE_KEY = "neurolegal.sidebarWidth";

export const SIDEBAR_MIN_WIDTH = 220;
export const SIDEBAR_MAX_WIDTH = 360;
export const SIDEBAR_DEFAULT_WIDTH = 264;

export function clampSidebarWidth(w: number): number {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Math.round(w)));
}

export function loadSidebarWidth(): number {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return SIDEBAR_DEFAULT_WIDTH;
    const n = Number(JSON.parse(raw));
    return Number.isFinite(n) ? clampSidebarWidth(n) : SIDEBAR_DEFAULT_WIDTH;
  } catch {
    return SIDEBAR_DEFAULT_WIDTH;
  }
}

export function saveSidebarWidth(w: number): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(clampSidebarWidth(w)));
  } catch {
    /* ignore quota/availability errors */
  }
}
