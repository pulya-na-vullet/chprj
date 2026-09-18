import { describe, expect, it } from "vitest";
import { formatDate, shortDate } from "../components/files/format";

describe("formatDate", () => {
  it("отдаёт «17 авг 2026» без точек сокращения и без «г.» (Minor 13)", () => {
    expect(formatDate("2026-08-17T10:00:00Z")).toBe("17 авг 2026");
  });

  it("не оставляет точек в сокращениях других месяцев", () => {
    expect(formatDate("2026-01-05T10:00:00Z")).not.toMatch(/\./);
    expect(formatDate("2026-11-05T10:00:00Z")).not.toMatch(/\./);
  });
});

describe("shortDate", () => {
  it("отдаёт «17 авг» без года и без точки", () => {
    expect(shortDate("2026-08-17T10:00:00Z")).toBe("17 авг");
  });
});
