import type { ReviewRisk } from "../../api/types";

/** Порядок и словесные метки уровней риска — общие для ReviewRunCard
 * (сводные счётчики) и ReviewPanel (строки аккордеона), T-0010. */
export const LEVEL_ORDER: ReviewRisk["level"][] = ["high", "medium", "low"];

export const LEVEL_LABELS: Record<ReviewRisk["level"], string> = {
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
};

/** Точка-индикатор уровня: слово — носитель смысла, точка — цветовой усилитель. */
export function LevelDot({ level }: { level: ReviewRisk["level"] }) {
  return <span className={`rvc-dot rvc-dot-${level}`} aria-hidden />;
}
