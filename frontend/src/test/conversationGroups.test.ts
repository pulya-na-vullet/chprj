import { describe, expect, it } from "vitest";
import { groupConversationsByTime } from "../state/conversationGroups";

const now = new Date("2026-06-27T12:00:00");
const mk = (id: string, iso: string) => ({ id, title: id, updated_at: iso });

describe("groupConversationsByTime", () => {
  it("splits into Сегодня / Вчера / Ранее and preserves order", () => {
    const groups = groupConversationsByTime(
      [
        mk("a", "2026-06-27T09:00:00"),
        mk("b", "2026-06-26T23:00:00"),
        mk("c", "2026-06-01T09:00:00"),
      ],
      now,
    );
    expect(groups.map((g) => g.label)).toEqual(["Сегодня", "Вчера", "Ранее"]);
    expect(groups[0].items.map((i) => i.id)).toEqual(["a"]);
    expect(groups[1].items.map((i) => i.id)).toEqual(["b"]);
    expect(groups[2].items.map((i) => i.id)).toEqual(["c"]);
  });

  it("omits empty groups", () => {
    const groups = groupConversationsByTime([mk("a", "2026-06-27T09:00:00")], now);
    expect(groups.map((g) => g.label)).toEqual(["Сегодня"]);
  });

  it("puts unparseable dates into Ранее", () => {
    const groups = groupConversationsByTime([mk("x", "not-a-date")], now);
    expect(groups).toEqual([{ label: "Ранее", items: [{ id: "x", title: "x", updated_at: "not-a-date" }] }]);
  });
});
