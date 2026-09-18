// Генеративные аватар-пресеты (T-0127, спека E19 §3.3): детерминированная
// функция от индекса пресета, 6 палитр, инициалы из имени+фамилии.
import { describe, expect, it } from "vitest";
import { AVATAR_PRESETS, initialsOf, presetBackground } from "../util/avatarPreset";

describe("avatarPreset (T-0127)", () => {
  it("ровно 6 пресетов; тёмные инициалы только у золото-беж (индекс 3)", () => {
    expect(AVATAR_PRESETS).toHaveLength(6);
    expect(AVATAR_PRESETS.map((p) => p.ink)).toEqual([
      "light",
      "light",
      "light",
      "dark",
      "light",
      "light",
    ]);
  });

  it("фон детерминирован и различен между пресетами", () => {
    const first = presetBackground(0, "lg");
    const again = presetBackground(0, "lg");
    expect(again).toEqual(first);

    const all = AVATAR_PRESETS.map((_p, i) => presetBackground(i, "lg").backgroundImage);
    expect(new Set(all).size).toBe(6);
  });

  it("слои: шум feTurbulence + геометрия + три radial-градиента + базовый тон", () => {
    const { backgroundImage, backgroundBlendMode } = presetBackground(2, "lg");
    expect(backgroundImage).toContain("feTurbulence");
    expect(backgroundImage.match(/radial-gradient/g)).toHaveLength(3);
    expect(backgroundImage).toContain("linear-gradient");
    // шум смешивается в overlay, остальные слои обычные
    expect(backgroundBlendMode.startsWith("overlay")).toBe(true);
  });

  it("масштаб зерна зависит от размера отрисовки (60px аватар vs 26px свотч)", () => {
    const lg = presetBackground(0, "lg").backgroundSize;
    const sm = presetBackground(0, "sm").backgroundSize;
    expect(lg).not.toEqual(sm);
  });

  it("инициалы собираются из имени и фамилии, в верхнем регистре", () => {
    expect(initialsOf("денис", "анастасьев")).toBe("ДА");
    expect(initialsOf("Ася", "")).toBe("А");
    expect(initialsOf("", "Иванова")).toBe("И");
    expect(initialsOf("", "")).toBe("");
    expect(initialsOf(null, undefined)).toBe("");
    expect(initialsOf("  денис  ", " а ")).toBe("ДА");
  });
});
