import { beforeEach, describe, expect, it } from "vitest";
import { loadViewMode, saveViewMode } from "../components/files/viewMode";

describe("viewMode", () => {
  beforeEach(() => localStorage.clear());

  it("по умолчанию список", () => {
    expect(loadViewMode()).toBe("list");
  });

  it("сохраняет и восстанавливает выбор", () => {
    saveViewMode("grid");
    expect(loadViewMode()).toBe("grid");
  });

  it("игнорирует мусор в хранилище", () => {
    localStorage.setItem("neurolegal.files.view", "нечто");
    expect(loadViewMode()).toBe("list");
  });
});
