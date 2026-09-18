// Геометрия спотлайта (T-0132, спека E19 §9): вырез = контур цели +6px со
// всех сторон, радиус цели +6; карточка-подсказка не вылезает за вьюпорт.
import { describe, expect, it } from "vitest";
import { CUT_PAD, cutRectFor, tipPositionFor } from "../tour/tourGeometry";

const target = { left: 100, top: 200, width: 320, height: 40 };

describe("tourGeometry (T-0132)", () => {
  it("вырез расширяет контур цели на 6px со всех сторон, радиус +6", () => {
    expect(CUT_PAD).toBe(6);
    const cut = cutRectFor(target, 10);
    expect(cut).toEqual({ left: 94, top: 194, width: 332, height: 52, radius: 16 });
  });

  it("радиус пилюли (999px «с запасом») клампится к фактической полувысоте", () => {
    // Иначе SVG-дырка и CSS-рамка клампят по-разному (эллипс против круга),
    // и по бокам выреза остаются тёмные серпы.
    const pill = cutRectFor({ left: 100, top: 200, width: 180, height: 40 }, 999);
    expect(pill.radius).toBe(26); // min(999, 40/2) + 6
  });

  it("подсказка под целью центрируется по вырезу", () => {
    const cut = cutRectFor(target, 10);
    const pos = tipPositionFor(cut, { width: 300, height: 120 }, { width: 1280, height: 800 }, "below");
    expect(pos.top).toBe(cut.top + cut.height + 16);
    expect(pos.left).toBe(Math.round(cut.left + cut.width / 2 - 150));
  });

  it("подсказка справа от цели выравнивается по верху выреза", () => {
    const cut = cutRectFor(target, 10);
    const pos = tipPositionFor(cut, { width: 300, height: 120 }, { width: 1280, height: 800 }, "right");
    expect(pos.left).toBe(cut.left + cut.width + 16);
    expect(pos.top).toBe(cut.top);
  });

  it("нет места снизу — карточка переворачивается над вырезом (чат-режим)", () => {
    // Композер открытого чата прижат к низу экрана: «below» уложил бы
    // карточку поверх выделения после зажима.
    const cut = cutRectFor({ left: 300, top: 700, width: 600, height: 60 }, 20);
    const pos = tipPositionFor(cut, { width: 300, height: 160 }, { width: 1280, height: 800 }, "below");
    expect(pos.top).toBe(cut.top - 160 - 16);
  });

  it("позиция зажимается в границы вьюпорта с полем 12px", () => {
    const cut = cutRectFor({ left: 1200, top: 760, width: 60, height: 30 }, 8);
    const pos = tipPositionFor(cut, { width: 300, height: 140 }, { width: 1280, height: 800 }, "below");
    expect(pos.left + 300).toBeLessThanOrEqual(1280 - 12);
    expect(pos.top + 140).toBeLessThanOrEqual(800 - 12);
    expect(pos.left).toBeGreaterThanOrEqual(12);
    expect(pos.top).toBeGreaterThanOrEqual(12);
  });
});
