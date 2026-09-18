export type FilesViewMode = "list" | "grid";

const KEY = "neurolegal.files.view";

/** Выбранный вид переживает перезагрузку; чужое значение в хранилище
 * не должно ломать раздел — падаем в список. */
export function loadViewMode(): FilesViewMode {
  try {
    return localStorage.getItem(KEY) === "grid" ? "grid" : "list";
  } catch {
    return "list";
  }
}

export function saveViewMode(mode: FilesViewMode): void {
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    /* приватный режим — вид просто не запомнится */
  }
}
