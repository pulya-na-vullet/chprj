import type { HubDocumentInfo } from "../../api/types";

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1).replace(".", ",")} КБ`;
  return `${(kb / 1024).toFixed(1).replace(".", ",")} МБ`;
}

// ru-RU отдаёт «17 авг. 2026 г.» — спека хочет «17 авг 2026» без точек
// (Minor 13, финальное ревью): срезаем точки сокращений и висящее «г.».
export function formatDate(iso: string): string {
  // \b не годится: JS-регэксп по умолчанию не считает кириллицу словом
  // (\w — только ASCII), поэтому «г» на границе с пробелом не матчится —
  // якорим на конец строки, «г.» в ru-RU формате всегда завершающее.
  return new Date(iso)
    .toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" })
    .replace(/\./g, "")
    .replace(/\s*г$/, "");
}

// Короткая дата без года — нижняя строка карточки плитки («248 КБ · 17 авг»).
export function shortDate(iso: string): string {
  return new Date(iso)
    .toLocaleDateString("ru-RU", { day: "numeric", month: "short" })
    .replace(/\.$/, "");
}

// «Суть» — серверная LLM-выжимка (T-0017); NULL → прочерк (LLM недоступен
// или выжимка ещё догоняет — поллинг в FilesView подтянет). Общая для
// строки списка и карточки плитки (Minor 19, финальное ревью — раньше жила
// побайтово одинаковой копией в обоих местах).
export function summaryLabel(d: HubDocumentInfo): string {
  if (d.status === "failed") return humanizeDocError(d.error);
  if (d.status === "processing") return "Извлекаем текст…";
  return d.summary || "—";
}

// Сырые сообщения пайплайна извлечения («File is not a zip file») не показываем
// пользователю — переводим типовые случаи в действие, остальное сводим к общей
// формулировке.
export function humanizeDocError(error: string | null | undefined): string {
  if (error && /not a zip file/i.test(error))
    return "Файл имеет расширение .docx, но не является документом Word. Загрузите исходный файл.";
  return "Не удалось обработать документ. Попробуйте загрузить файл заново.";
}
