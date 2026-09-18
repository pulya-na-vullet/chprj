// Стейт-машина тура (T-0132, спека E19 §9): 4 шага спотлайта → финал;
// пропуск из любого шага; счётчик пилюли хранит максимум пройденного;
// автоскрытие пилюли после трёх заданных вопросов.
import { describe, expect, it } from "vitest";
import {
  TOUR_STEPS,
  initialTourState,
  isPillVisible,
  pillLabel,
  tourReducer,
} from "../tour/tourMachine";

describe("tourMachine (T-0132)", () => {
  it("4 шага в порядке спеки: композер → источники → файлы → проверки", () => {
    expect(TOUR_STEPS.map((s) => s.key)).toEqual(["composer", "sources", "files", "reviews"]);
  });

  it("START входит в первый шаг и отмечает его пройденным", () => {
    const s = tourReducer(initialTourState, { type: "START" });
    expect(s.status).toBe("steps");
    expect(s.step).toBe(0);
    expect(s.maxSeen).toBe(1);
  });

  it("NEXT идёт по шагам, с последнего — в финал с maxSeen=4", () => {
    let s = tourReducer(initialTourState, { type: "START" });
    s = tourReducer(s, { type: "NEXT" });
    expect(s.step).toBe(1);
    expect(s.maxSeen).toBe(2);
    s = tourReducer(s, { type: "NEXT" });
    s = tourReducer(s, { type: "NEXT" });
    expect(s.step).toBe(3);
    s = tourReducer(s, { type: "NEXT" });
    expect(s.status).toBe("finale");
    expect(s.maxSeen).toBe(4);
  });

  it("SKIP завершает тур из любого шага, maxSeen не растёт", () => {
    let s = tourReducer(initialTourState, { type: "START" });
    s = tourReducer(s, { type: "NEXT" });
    s = tourReducer(s, { type: "SKIP" });
    expect(s.status).toBe("done");
    expect(s.skipped).toBe(true);
    expect(s.maxSeen).toBe(2);
  });

  it("повторный START (с пилюли) начинает сначала, сохраняя максимум", () => {
    let s = tourReducer(initialTourState, { type: "START" });
    for (let i = 0; i < 4; i += 1) s = tourReducer(s, { type: "NEXT" });
    expect(s.status).toBe("finale");
    s = tourReducer(s, { type: "START" });
    expect(s.status).toBe("steps");
    expect(s.step).toBe(0);
    expect(s.maxSeen).toBe(4); // максимум не сбрасывается
  });

  it("метка пилюли — максимум пройденного из четырёх", () => {
    expect(pillLabel(0)).toBe("0/4");
    expect(pillLabel(2)).toBe("2/4");
    expect(pillLabel(7)).toBe("4/4");
  });

  it("пилюля видна до трёх заданных вопросов включительно-исключительно", () => {
    expect(isPillVisible(0)).toBe(true);
    expect(isPillVisible(2)).toBe(true);
    expect(isPillVisible(3)).toBe(false);
    expect(isPillVisible(10)).toBe(false);
  });
});
