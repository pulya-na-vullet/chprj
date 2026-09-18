import { InfoIcon } from "./InfoIcon";

export function SkillsSection() {
  return (
    <div className="scaffold-card">
      <div className="scaffold-head">
        Скиллы
        <InfoIcon text="Готовые «навыки» — связки из промпта и тулзов под конкретную задачу. Включаются переключателем." />
        <span className="soon-pill">скоро</span>
      </div>
      <p>
        Здесь появится список скиллов с переключателями и раскрытием настроек (как в «Тулзах»).
        Пока не реализовано.
      </p>
    </div>
  );
}
