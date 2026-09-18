import { afterEach, describe, expect, it } from "vitest";
import {
  clampSidebarWidth,
  loadSidebarWidth,
  saveSidebarWidth,
  SIDEBAR_DEFAULT_WIDTH,
} from "../state/sidebarWidth";

afterEach(() => localStorage.clear());

describe("sidebar width persistence", () => {
  it("clamps below min and above max", () => {
    expect(clampSidebarWidth(100)).toBe(220);
    expect(clampSidebarWidth(999)).toBe(360);
    expect(clampSidebarWidth(300)).toBe(300);
  });

  it("round-trips a saved width", () => {
    saveSidebarWidth(300);
    expect(loadSidebarWidth()).toBe(300);
  });

  it("returns the default when nothing is stored", () => {
    expect(loadSidebarWidth()).toBe(SIDEBAR_DEFAULT_WIDTH);
  });

  it("returns the default on a corrupt value", () => {
    localStorage.setItem("neurolegal.sidebarWidth", "not-json");
    expect(loadSidebarWidth()).toBe(SIDEBAR_DEFAULT_WIDTH);
  });
});
