// Пилюля «Тур по продукту · N/4» (T-0132, спека E19 §9): низ сайдбара над
// блоком аккаунта; во время тура остаётся под затемнением; после полного
// завершения по контуру дважды пробегает искра (CSS-анимация ×2); клик —
// перезапуск. Чистый компонент — состояние живёт в TourProvider.

export function TourPill({
  visible,
  compact,
  label,
  celebrate,
  onStart,
}: {
  visible: boolean;
  compact: boolean;
  label: string;
  celebrate: boolean;
  onStart: () => void;
}) {
  if (!visible) return null;
  return (
    <button
      type="button"
      className={celebrate ? "tour-pill tour-pill-celebrate" : "tour-pill"}
      onClick={onStart}
      aria-label={`Тур по продукту, пройдено ${label}`}
      title="Запустить интерактивный тур"
    >
      {!compact && <span className="tour-pill-t">Тур по продукту</span>}
      <span className="tour-pill-cnt">{label}</span>
    </button>
  );
}
