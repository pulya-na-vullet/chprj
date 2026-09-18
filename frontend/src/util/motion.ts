/** Системная просьба «меньше движения». CSS гасит переходы сам
 * (@media prefers-reduced-motion), но цепочки таймеров в JS без этой
 * проверки остаются паузами без анимации — ждать нечего, а ждём. */
export function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}
