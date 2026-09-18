import { describe, expect, it } from "vitest";
import { applyServerEvent, chatReducer, initialState } from "../state/chatReducer";
import type { Message, ServerEvent } from "../api/types";

describe("applyServerEvent", () => {
  it("reasoning sets the working label to Думаю", () => {
    const s = applyServerEvent(initialState, { event: "reasoning", data: { text: "…" } });
    expect(s.working?.label).toBe("Думаю");
  });

  it("tool_call sets the searching label", () => {
    const s = applyServerEvent(initialState, {
      event: "tool_call",
      data: { tool: "rag_search", args: {}, error: false },
    });
    expect(s.working?.label).toBe("Ищу в законодательстве…");
  });

  it("tool_result with found numbers sets the studying label", () => {
    const s = applyServerEvent(initialState, {
      event: "tool_result",
      data: { found: [{ act: "ГК РФ", number: "1477" }, { act: "ГК РФ", number: "1481" }] },
    });
    expect(s.working?.label).toBe("Изучаю ст. 1477, 1481…");
  });

  it("delta clears the working line and appends draft answer", () => {
    let s = applyServerEvent(initialState, { event: "reasoning", data: { text: "x" } });
    s = applyServerEvent(s, { event: "delta", data: { text: "Привет" } });
    expect(s.working).toBeNull();
    expect(s.draftAnswer).toBe("Привет");
  });

  // T-0102, пункт 8: накопление проверялось ОДНОЙ дельтой, поэтому версия
  // «draftAnswer = ev.data.text» проходила — а в ней от ответа остаётся
  // только последний токен.
  it("delta accumulates across chunks instead of replacing the draft", () => {
    let s = applyServerEvent(initialState, { event: "delta", data: { text: "Соглас" } });
    s = applyServerEvent(s, { event: "delta", data: { text: "но ст. 1477" } });
    s = applyServerEvent(s, { event: "delta", data: { text: " ГК РФ" } });
    expect(s.draftAnswer).toBe("Согласно ст. 1477 ГК РФ");
  });

  // Бэкенд может выкатить новый тип события раньше фронта. Без ветки default
  // switch вернул бы undefined — и оно стало бы всем состоянием чата.
  it("ignores an unknown event type instead of wiping the state", () => {
    const before = applyServerEvent(initialState, { event: "delta", data: { text: "ответ" } });
    const after = applyServerEvent(before, {
      event: "quantum_flux",
      data: { whatever: true },
    } as unknown as ServerEvent);
    expect(after).toBe(before);
    expect(after.draftAnswer).toBe("ответ");
  });

  it("reset_delta clears draftAnswer, working, and draftCitations", () => {
    let s = applyServerEvent(initialState, { event: "delta", data: { text: "промежуточно" } });
    s = applyServerEvent(s, {
      event: "citations",
      data: { articles: [{ act_short_name: "ГК РФ", kind: "codex", number: "1", title: null, full_text: "t", score: 0.1 }] },
    });
    expect(s.draftAnswer).toBe("промежуточно");
    expect(s.draftCitations).toHaveLength(1);
    s = applyServerEvent(s, { event: "reset_delta", data: {} });
    expect(s.draftAnswer).toBe("");
    expect(s.draftCitations).toEqual([]);
    expect(s.working).toBeNull();
  });

  it("citations are stored as draft", () => {
    const s = applyServerEvent(initialState, {
      event: "citations",
      data: { articles: [{ act_short_name: "ГК РФ", kind: "codex", number: "1", title: null, full_text: "t", score: 0.1 }] },
    });
    expect(s.draftCitations).toHaveLength(1);
  });

  it("web tool_call sets the internet-search label", () => {
    const s = applyServerEvent(initialState, {
      event: "tool_call",
      data: { tool: "web_search", args: {}, error: false },
    });
    expect(s.working?.label).toBe("Ищу в интернете…");
    expect(s.toolIsWeb).toBe(true);
  });

  it("tool_result after a web tool never reads as 'nothing found'", () => {
    let s = applyServerEvent(initialState, {
      event: "tool_call",
      data: { tool: "web_search", args: {}, error: false },
    });
    s = applyServerEvent(s, { event: "tool_result", data: { found: [] } });
    expect(s.working?.label).toBe("Просматриваю источники из интернета…");
  });

  it("web_sources are stored as draft", () => {
    const s = applyServerEvent(initialState, {
      event: "web_sources",
      data: { sources: [{ url: "https://e.gov", title: "T", snippet: "s" }] },
    });
    expect(s.draftWebSources).toHaveLength(1);
    expect(s.draftWebSources[0].url).toBe("https://e.gov");
  });

  it("reset_delta clears draftWebSources too", () => {
    let s = applyServerEvent(initialState, {
      event: "web_sources",
      data: { sources: [{ url: "https://e.gov", title: "T", snippet: null }] },
    });
    s = applyServerEvent(s, { event: "reset_delta", data: {} });
    expect(s.draftWebSources).toEqual([]);
  });

  it("review_progress numeric index stays monotonic under concurrent running/done interleaving", () => {
    // With concurrency 4: running events carry a start-order counter
    // (1,2,3,4…) while final events carry a completion-order counter
    // (1,2,3…) — the two sequences interleave. The displayed index must
    // never go backwards; only final ("done"/etc, i.e. non-"running")
    // events may advance it.
    function running(index: number, rule: string) {
      return applyServerEvent(s, {
        event: "review_progress" as const,
        data: { index, rule_id: rule, status: "running" as const, title: `Правило ${rule}`, total: 12 },
      });
    }
    function done(index: number, rule: string) {
      return applyServerEvent(s, {
        event: "review_progress" as const,
        data: { index, rule_id: rule, status: "ok" as const, title: `Правило ${rule} готово`, total: 12 },
      });
    }

    let s = initialState;
    const indices: number[] = [];
    const titles: string[] = [];

    s = running(1, "r1");
    indices.push(s.reviewProgress!.index);
    titles.push(s.reviewProgress!.title);

    s = running(2, "r2");
    indices.push(s.reviewProgress!.index);
    titles.push(s.reviewProgress!.title);

    s = running(3, "r3");
    indices.push(s.reviewProgress!.index);
    titles.push(s.reviewProgress!.title);

    s = running(4, "r4");
    indices.push(s.reviewProgress!.index);
    titles.push(s.reviewProgress!.title);

    s = done(1, "r1");
    indices.push(s.reviewProgress!.index);
    titles.push(s.reviewProgress!.title);

    s = running(5, "r5");
    indices.push(s.reviewProgress!.index);
    titles.push(s.reviewProgress!.title);

    s = done(2, "r2");
    indices.push(s.reviewProgress!.index);
    titles.push(s.reviewProgress!.title);

    // Numeric progress never decreases across the whole sequence.
    for (let i = 1; i < indices.length; i++) {
      expect(indices[i]).toBeGreaterThanOrEqual(indices[i - 1]);
    }
    expect(indices).toEqual([0, 0, 0, 0, 1, 1, 2]);
    // Title tracks the latest event of any kind (running or done).
    expect(titles).toEqual([
      "Правило r1",
      "Правило r2",
      "Правило r3",
      "Правило r4",
      "Правило r1 готово",
      "Правило r5",
      "Правило r2 готово",
    ]);
  });

  it("ask stores question+options as draftAsk and mirrors the question into draftAnswer", () => {
    const s = applyServerEvent(initialState, {
      event: "ask",
      data: {
        question: "Кто вы по этому договору?",
        options: ["Покупатель", "Поставщик"],
        allow_free_text: true,
        kind: "review_role",
        template: false,
      },
    });
    expect(s.draftAsk).toEqual({
      question: "Кто вы по этому договору?",
      options: ["Покупатель", "Поставщик"],
      allow_free_text: true,
      kind: "review_role",
      template: false,
    });
    expect(s.draftAnswer).toBe("Кто вы по этому договору?");
  });
});

function makeUser(content: string): Message {
  return {
    id: crypto.randomUUID(),
    role: "user",
    content,
    citations: null,
    stopped: false,
    created_at: new Date().toISOString(),
  };
}

describe("turnId discriminator", () => {
  const userMsg = {
    id: "u1",
    role: "user" as const,
    content: "hi",
    citations: null,
    stopped: false,
    created_at: "2026-06-01T00:00:00Z",
  };

  it("START_TURN increments turnId", () => {
    const s1 = chatReducer(initialState, { type: "START_TURN", user: userMsg });
    expect(s1.turnId).toBe(initialState.turnId + 1);
    const s2 = chatReducer(s1, {
      type: "START_TURN",
      user: { ...userMsg, id: "u2", content: "again" },
    });
    expect(s2.turnId).toBe(s1.turnId + 1);
  });

  it("SSE action with stale turnId is ignored", () => {
    const s1 = chatReducer(initialState, { type: "START_TURN", user: userMsg });
    const stale = chatReducer(s1, {
      type: "SSE",
      turnId: s1.turnId - 1,
      ev: { event: "delta", data: { text: "stale" } },
    });
    expect(stale.draftAnswer).toBe("");
  });

  it("SSE action with matching turnId is applied", () => {
    const s1 = chatReducer(initialState, { type: "START_TURN", user: userMsg });
    const after = chatReducer(s1, {
      type: "SSE",
      turnId: s1.turnId,
      ev: { event: "delta", data: { text: "live" } },
    });
    expect(after.draftAnswer).toBe("live");
  });

  it("NEW_CHAT increments turnId so any in-flight SSE becomes stale", () => {
    const s1 = chatReducer(initialState, { type: "START_TURN", user: userMsg });
    const s2 = chatReducer(s1, { type: "NEW_CHAT" });
    expect(s2.turnId).toBeGreaterThan(s1.turnId);
  });

  it("OPEN_CONVERSATION increments turnId and clears draft/streaming", () => {
    let s = chatReducer(initialState, { type: "START_TURN", user: userMsg });
    s = chatReducer(s, {
      type: "SSE",
      turnId: s.turnId,
      ev: { event: "delta", data: { text: "wip" } },
    });
    expect(s.draftAnswer).toBe("wip");
    const opened = chatReducer(s, { type: "OPEN_CONVERSATION", id: "c2", messages: [] });
    expect(opened.turnId).toBeGreaterThan(s.turnId);
    expect(opened.draftAnswer).toBe("");
    expect(opened.streaming).toBe(false);
  });
});

describe("stop generation", () => {
  it("done(stopped) + непустой черновик → сообщение финализируется со stopped", () => {
    let s = chatReducer(initialState, { type: "START_TURN", user: makeUser("вопрос") });
    s = chatReducer(s, { type: "SSE", turnId: s.turnId, ev: { event: "delta", data: { text: "частичный" } } });
    s = chatReducer(s, {
      type: "SSE",
      turnId: s.turnId,
      ev: { event: "done", data: { message_id: "m1", stopped: true } },
    });
    s = chatReducer(s, { type: "FINISH_TURN", turnId: s.turnId });
    const last = s.messages[s.messages.length - 1];
    expect(last.role).toBe("assistant");
    expect(last.content).toBe("частичный");
    expect(last.stopped).toBe(true);
    expect(s.streaming).toBe(false);
    expect(s.stopping).toBe(false);
  });

  it("done(stopped) + пустой черновик → assistant-сообщение не добавляется", () => {
    let s = chatReducer(initialState, { type: "START_TURN", user: makeUser("вопрос") });
    s = chatReducer(s, {
      type: "SSE",
      turnId: s.turnId,
      ev: { event: "done", data: { message_id: null, stopped: true } },
    });
    s = chatReducer(s, { type: "FINISH_TURN", turnId: s.turnId });
    expect(s.messages.map((m) => m.role)).toEqual(["user"]);
  });

  it("STOP_REQUESTED ставит stopping только во время стрима", () => {
    expect(chatReducer(initialState, { type: "STOP_REQUESTED" }).stopping).toBe(false);
    let s = chatReducer(initialState, { type: "START_TURN", user: makeUser("q") });
    s = chatReducer(s, { type: "STOP_REQUESTED" });
    expect(s.stopping).toBe(true);
  });
});

describe("SET_BANNER", () => {
  it("sets the banner without touching streaming/draft state", () => {
    const mid = chatReducer(initialState, {
      type: "START_TURN",
      user: {
        id: "u1",
        role: "user",
        content: "hi",
        citations: null,
        stopped: false,
        created_at: "2026-06-06T00:00:00Z",
      },
    });
    const after = chatReducer(mid, { type: "SET_BANNER", banner: "boom" });
    expect(after.banner).toBe("boom");
    expect(after.streaming).toBe(true);          // unchanged
    expect(after.pendingUser).not.toBeNull();    // unchanged
    expect(after.turnId).toBe(mid.turnId);       // unchanged
  });
});

describe("resource statuses", () => {
  it("acts loading → ready", () => {
    const s1 = chatReducer(initialState, { type: "ACTS_LOADING" });
    expect(s1.actsStatus).toBe("loading");
    const s2 = chatReducer(s1, {
      type: "SET_ACTS",
      acts: ["ГК РФ"],
      selected: ["ГК РФ"],
    });
    expect(s2.actsStatus).toBe("ready");
    expect(s2.actsError).toBeNull();
  });

  it("acts loading → error sets actsError, keeps prior acts", () => {
    const s1 = chatReducer(
      { ...initialState, acts: ["existing"], actsStatus: "ready" },
      { type: "ACTS_FAILED", error: "Не удалось загрузить источники" },
    );
    expect(s1.actsStatus).toBe("error");
    expect(s1.actsError).toBe("Не удалось загрузить источники");
    expect(s1.acts).toEqual(["existing"]);
  });

  it("conversations loading → ready", () => {
    const s1 = chatReducer(initialState, { type: "CONVERSATIONS_LOADING" });
    expect(s1.conversationsStatus).toBe("loading");
    const s2 = chatReducer(s1, { type: "SET_CONVERSATIONS", items: [] });
    expect(s2.conversationsStatus).toBe("ready");
  });

  it("conversations failure keeps prior items", () => {
    const s1 = chatReducer(
      {
        ...initialState,
        conversations: [{ id: "c", title: "t", updated_at: "" }],
      },
      { type: "CONVERSATIONS_FAILED", error: "сервер недоступен" },
    );
    expect(s1.conversationsStatus).toBe("error");
    expect(s1.conversationsError).toBe("сервер недоступен");
    expect(s1.conversations.length).toBe(1);
  });
});

describe("review panel + retry context", () => {
  it("OPEN_REVIEW_PANEL / CLOSE_REVIEW_PANEL toggle reviewPanelFor", () => {
    let s = chatReducer(initialState, { type: "OPEN_REVIEW_PANEL", messageId: "m1" });
    expect(s.reviewPanelFor).toBe("m1");
    s = chatReducer(s, { type: "CLOSE_REVIEW_PANEL" });
    expect(s.reviewPanelFor).toBeNull();
  });

  it("SET_REVIEW_REQUEST stores the retry context", () => {
    const s = chatReducer(initialState, {
      type: "SET_REVIEW_REQUEST",
      request: {
        documentId: "d1",
        playbookId: "supply_ru",
        label: "Проверить риски",
        turnId: 1,
        role: null,
      },
    });
    expect(s.lastReviewRequest).toEqual({
      documentId: "d1",
      playbookId: "supply_ru",
      label: "Проверить риски",
      turnId: 1,
      role: null,
    });
  });

  it("SET_REVIEW_REQUEST stores a known role (T-0046: answered via AskBlock)", () => {
    const s = chatReducer(initialState, {
      type: "SET_REVIEW_REQUEST",
      request: {
        documentId: "d1",
        playbookId: "supply_ru",
        label: "",
        turnId: 1,
        role: "Покупатель",
      },
    });
    expect(s.lastReviewRequest?.role).toBe("Покупатель");
  });

  // Reworked (was: gated on reviewProgress !== null): an early pipeline
  // failure ("Документ не найден") fires *before* any review_progress event,
  // so the old check missed it. reviewFailed is now keyed on turnId — set by
  // SET_REVIEW_REQUEST for the turn about to start (mirrors ChatContext.
  // sendReview's ordering: SET_REVIEW_REQUEST dispatches before START_TURN,
  // stamping the turnId the upcoming START_TURN will assign).
  it("TURN_FAILED during an active review run captures reviewFailed, cleared on the next turn", () => {
    let s = chatReducer(initialState, {
      type: "SET_REVIEW_REQUEST",
      request: {
        documentId: "d1",
        playbookId: "supply_ru",
        label: "x",
        turnId: initialState.turnId + 1,
        role: null,
      },
    });
    s = chatReducer(s, { type: "START_TURN", user: makeUser("проверь риски") });
    s = {
      ...s,
      reviewProgress: { index: 1, rule_id: "r1", status: "running", title: "Правило r1", total: 3 },
    };
    s = chatReducer(s, { type: "TURN_FAILED", turnId: s.turnId, banner: "boom" });
    expect(s.reviewFailed).toEqual({ detail: "boom" });
    expect(s.reviewProgress).toBeNull();

    s = chatReducer(s, { type: "START_TURN", user: makeUser("ещё раз") });
    expect(s.reviewFailed).toBeNull();
    // START_TURN does not clear lastReviewRequest — the next sendReview overwrites it.
    expect(s.lastReviewRequest).toEqual({
      documentId: "d1",
      playbookId: "supply_ru",
      label: "x",
      turnId: initialState.turnId + 1,
      role: null,
    });
  });

  // New coverage (fixes the concern from Task 1): a review turn that fails
  // *before* the first review_progress event ever arrives — e.g. "Документ
  // не найден" / "Сервис документов недоступен" from the pipeline — must
  // still surface as a failed-review card, not silently as a plain banner.
  it("TURN_FAILED before any review_progress event still captures reviewFailed", () => {
    let s = chatReducer(initialState, {
      type: "SET_REVIEW_REQUEST",
      request: {
        documentId: "d1",
        playbookId: "supply_ru",
        label: "x",
        turnId: initialState.turnId + 1,
        role: null,
      },
    });
    s = chatReducer(s, { type: "START_TURN", user: makeUser("проверь риски") });
    expect(s.reviewProgress).toBeNull(); // no progress event happened yet
    s = chatReducer(s, { type: "TURN_FAILED", turnId: s.turnId, banner: "Документ не найден" });
    expect(s.reviewFailed).toEqual({ detail: "Документ не найден" });
  });

  it("TURN_FAILED without an active review run leaves reviewFailed null (regular chat turn)", () => {
    let s = chatReducer(initialState, { type: "START_TURN", user: makeUser("обычный вопрос") });
    s = chatReducer(s, { type: "TURN_FAILED", turnId: s.turnId, banner: "boom" });
    expect(s.reviewFailed).toBeNull();
  });

  it("TURN_FAILED for a later plain turn doesn't resurrect a stale review's reviewFailed", () => {
    // lastReviewRequest survives past its own turn (by design — retry needs
    // it) but its turnId now belongs to a finished review turn; a later
    // plain chat turn failing must not match it.
    let s = chatReducer(initialState, {
      type: "SET_REVIEW_REQUEST",
      request: {
        documentId: "d1",
        playbookId: "supply_ru",
        label: "x",
        turnId: initialState.turnId + 1,
        role: null,
      },
    });
    s = chatReducer(s, { type: "START_TURN", user: makeUser("проверь риски") });
    s = chatReducer(s, { type: "FINISH_TURN", turnId: s.turnId }); // review turn succeeds
    s = chatReducer(s, { type: "START_TURN", user: makeUser("обычный вопрос") });
    s = chatReducer(s, { type: "TURN_FAILED", turnId: s.turnId, banner: "boom" });
    expect(s.reviewFailed).toBeNull();
  });

  it("NEW_CHAT closes the panel and clears reviewFailed + lastReviewRequest", () => {
    const s = chatReducer(
      {
        ...initialState,
        reviewPanelFor: "m1",
        reviewFailed: { detail: "boom" },
        lastReviewRequest: {
          documentId: "d1",
          playbookId: "supply_ru",
          label: "x",
          turnId: 1,
          role: null,
        },
      },
      { type: "NEW_CHAT" },
    );
    expect(s.reviewPanelFor).toBeNull();
    expect(s.reviewFailed).toBeNull();
    expect(s.lastReviewRequest).toBeNull();
  });

  it("OPEN_CONVERSATION closes the panel and clears reviewFailed + lastReviewRequest", () => {
    const s = chatReducer(
      {
        ...initialState,
        reviewPanelFor: "m1",
        reviewFailed: { detail: "boom" },
        lastReviewRequest: {
          documentId: "d1",
          playbookId: "supply_ru",
          label: "x",
          turnId: 1,
          role: null,
        },
      },
      { type: "OPEN_CONVERSATION", id: "c2", messages: [] },
    );
    expect(s.reviewPanelFor).toBeNull();
    expect(s.reviewFailed).toBeNull();
    expect(s.lastReviewRequest).toBeNull();
  });
});

describe("ask → message.ask on FINISH_TURN (T-0046)", () => {
  it("merges draftAsk into the finalized assistant message as a review_role MessageAsk", () => {
    let s = chatReducer(initialState, {
      type: "START_TURN",
      user: makeUser("Проверить «файл»: Плейбук"),
    });
    s = chatReducer(s, {
      type: "SSE",
      turnId: s.turnId,
      ev: {
        event: "ask",
        data: {
          question: "Кто вы по этому договору?",
          options: ["Покупатель", "Поставщик"],
          allow_free_text: true,
          kind: "review_role",
          template: false,
        },
      },
    });
    s = chatReducer(s, {
      type: "SSE",
      turnId: s.turnId,
      ev: { event: "done", data: { message_id: "m1", stopped: false } },
    });
    s = chatReducer(s, { type: "FINISH_TURN", turnId: s.turnId });
    const last = s.messages[s.messages.length - 1];
    expect(last.role).toBe("assistant");
    expect(last.content).toBe("Кто вы по этому договору?");
    expect(last.ask).toEqual({
      kind: "review_role",
      question: "Кто вы по этому договору?",
      options: ["Покупатель", "Поставщик"],
      template: false,
    });
    expect(s.draftAsk).toBeNull();
  });

  it("no ask event this turn — finalized message.ask is null", () => {
    let s = chatReducer(initialState, { type: "START_TURN", user: makeUser("вопрос") });
    s = chatReducer(s, {
      type: "SSE",
      turnId: s.turnId,
      ev: { event: "delta", data: { text: "ответ" } },
    });
    s = chatReducer(s, { type: "FINISH_TURN", turnId: s.turnId });
    expect(s.messages[s.messages.length - 1].ask ?? null).toBeNull();
  });

  it("draftAsk is cleared on START_TURN, NEW_CHAT, OPEN_CONVERSATION", () => {
    let s = chatReducer(initialState, { type: "START_TURN", user: makeUser("q1") });
    s = chatReducer(s, {
      type: "SSE",
      turnId: s.turnId,
      ev: {
        event: "ask",
        data: { question: "Q", options: [], allow_free_text: true, kind: "review_role", template: false },
      },
    });
    expect(s.draftAsk).not.toBeNull();

    expect(chatReducer(s, { type: "NEW_CHAT" }).draftAsk).toBeNull();
    expect(chatReducer(s, { type: "OPEN_CONVERSATION", id: "c2", messages: [] }).draftAsk).toBeNull();
    expect(chatReducer(s, { type: "START_TURN", user: makeUser("q2") }).draftAsk).toBeNull();
  });

  it("FINISH_TURN сохраняет kind живого ask_user (T-0051)", () => {
    let s = chatReducer(initialState, {
      type: "START_TURN",
      user: makeUser("перепиши претензию"),
    });
    s = chatReducer(s, {
      type: "SSE",
      turnId: s.turnId,
      ev: {
        event: "ask",
        data: {
          question: "Для кого письмо?",
          options: ["Клиенту"],
          allow_free_text: true,
          kind: "ask_user",
          template: false,
        },
      },
    });
    s = chatReducer(s, { type: "FINISH_TURN", turnId: s.turnId });
    const last = s.messages[s.messages.length - 1];
    expect(last.ask?.kind).toBe("ask_user");
    expect(last.content).toBe("Для кого письмо?");
  });
});

describe("PREFILL_COMPOSER", () => {
  it("sets composerPrefill to the given text", () => {
    const s = chatReducer(initialState, {
      type: "PREFILL_COMPOSER",
      text: "Про риск «Неустойка за просрочку» (п. 6.2): ",
    });
    expect(s.composerPrefill).toBe("Про риск «Неустойка за просрочку» (п. 6.2): ");
  });

  it("empty string clears it back to null (Composer's consume-and-clear)", () => {
    const filled = chatReducer(initialState, { type: "PREFILL_COMPOSER", text: "x" });
    const cleared = chatReducer(filled, { type: "PREFILL_COMPOSER", text: "" });
    expect(cleared.composerPrefill).toBeNull();
  });
});

describe("view + sidebar width", () => {
  it("SET_VIEW switches the active view", () => {
    expect(chatReducer(initialState, { type: "SET_VIEW", view: "sources" }).view).toBe("sources");
  });

  it("NEW_CHAT resets the view to chat", () => {
    const s = { ...initialState, view: "files" as const };
    expect(chatReducer(s, { type: "NEW_CHAT" }).view).toBe("chat");
  });

  it("OPEN_CONVERSATION resets the view to chat", () => {
    const s = { ...initialState, view: "sources" as const };
    expect(chatReducer(s, { type: "OPEN_CONVERSATION", id: "x", messages: [] }).view).toBe("chat");
  });

  it("SET_SIDEBAR_WIDTH stores the width", () => {
    expect(chatReducer(initialState, { type: "SET_SIDEBAR_WIDTH", width: 300 }).sidebarWidth).toBe(300);
  });

  it("starts on the chat view", () => {
    expect(initialState.view).toBe("chat");
  });
});

describe("review request from Files (T-0148)", () => {
  it("OPEN_REVIEW_REQUEST переводит в раздел проверок и запоминает документ", () => {
    const next = chatReducer(initialState, { type: "OPEN_REVIEW_REQUEST", docId: "d7" });
    expect(next.view).toBe("reviews");
    expect(next.reviewRequestDocId).toBe("d7");

    const cleared = chatReducer(next, { type: "CLEAR_REVIEW_REQUEST" });
    expect(cleared.reviewRequestDocId).toBeNull();
  });
});
