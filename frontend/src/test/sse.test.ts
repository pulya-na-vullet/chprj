import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { onUnauthorized } from "../api/authEvents";
import { parseFrames, streamChat } from "../api/sse";

describe("parseFrames", () => {
  it("parses CRLF-separated frames", () => {
    const buf = "event: delta\r\ndata: {\"text\":\"hi\"}\r\n\r\n";
    const { events, rest } = parseFrames(buf);
    expect(events).toEqual([{ event: "delta", data: { text: "hi" } }]);
    expect(rest).toBe("");
  });

  it("parses LF-separated frames", () => {
    const { events } = parseFrames('event: done\ndata: {"message_id":"m"}\n\n');
    expect(events[0]).toEqual({ event: "done", data: { message_id: "m" } });
  });

  it("keeps a partial trailing frame in rest", () => {
    const { events, rest } = parseFrames('event: delta\ndata: {"text":"a"}\n\nevent: del');
    expect(events).toHaveLength(1);
    expect(rest).toBe("event: del");
  });

  it("skips comment lines and frames without data", () => {
    const { events } = parseFrames(": keepalive\n\nevent: ping\n\n");
    expect(events).toEqual([]);
  });
});

const originalFetch = globalThis.fetch;

function fetchStreamingBody(...frames: string[]): typeof fetch {
  return vi.fn(async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        for (const frame of frames) controller.enqueue(encoder.encode(frame));
        controller.close();
      },
    });
    return new Response(body, {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    });
  }) as typeof fetch;
}

describe("streamChat terminal-event tracking", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("returns done only when the `done` event arrived", async () => {
    globalThis.fetch = fetchStreamingBody(
      'event: delta\ndata: {"text":"a"}\n\n',
      'event: done\ndata: {"message_id":"m"}\n\n',
    );
    const outcome = await streamChat({ sessionId: null, message: "hi", acts: null }, () => {});
    expect(outcome).toBe("done");
  });

  it("returns interrupted on clean EOF without `done`", async () => {
    // A proxy idle-timeout closes the stream cleanly mid-answer: the partial
    // draft must NOT be finalized as a completed assistant message.
    globalThis.fetch = fetchStreamingBody('event: delta\ndata: {"text":"a"}\n\n');
    const outcome = await streamChat({ sessionId: null, message: "hi", acts: null }, () => {});
    expect(outcome).toBe("interrupted");
  });
});

// T-0102, пункт 8. Оба инварианта живут в СВЯЗКЕ streamChat+parseFrames и
// проверялись только на изолированном парсере, поэтому мутации в цикле чтения
// проходили молча.
describe("streamChat frame reassembly", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("reassembles an event split across network chunks", async () => {
    // TCP режет поток где угодно, в том числе посреди JSON. Если недочитанный
    // хвост не переносить в следующую итерацию (buffer = rest), событие
    // теряется целиком — у пользователя пропадает кусок ответа.
    globalThis.fetch = fetchStreamingBody(
      'event: delta\ndata: {"te',
      'xt":"Согласно ст. 1477"}\n\n',
      'event: done\ndata: {"message_id":"m"}\n\n',
    );
    const texts: string[] = [];
    const outcome = await streamChat({ sessionId: null, message: "hi", acts: null }, (ev) => {
      if (ev.event === "delta") texts.push(ev.data.text);
    });
    expect(texts).toEqual(["Согласно ст. 1477"]);
    expect(outcome).toBe("done");
  });

  it("keeps streaming after a malformed frame", async () => {
    // Один битый кадр (обрыв на стороне прокси, мусор в потоке) не имеет права
    // ронять весь ответ: без try/catch вокруг JSON.parse исключение уходит в
    // catch цикла чтения и весь ход становится network_error.
    globalThis.fetch = fetchStreamingBody(
      "event: delta\ndata: {не json}\n\n",
      'event: delta\ndata: {"text":"живой текст"}\n\n',
      'event: done\ndata: {"message_id":"m"}\n\n',
    );
    const texts: string[] = [];
    const outcome = await streamChat({ sessionId: null, message: "hi", acts: null }, (ev) => {
      if (ev.event === "delta") texts.push(ev.data.text);
    });
    expect(texts).toEqual(["живой текст"]);
    expect(outcome).toBe("done");
  });

  it("passes an unknown event type through to the consumer", async () => {
    // Фильтровать незнакомые события на транспорте нельзя: их игнорирует
    // редьюсер (ветка default), а транспорт обязан оставаться прозрачным.
    globalThis.fetch = fetchStreamingBody(
      'event: quantum_flux\ndata: {"x":1}\n\n',
      'event: done\ndata: {"message_id":"m"}\n\n',
    );
    const seen: string[] = [];
    const outcome = await streamChat({ sessionId: null, message: "hi", acts: null }, (ev) => {
      seen.push(ev.event);
    });
    expect(seen).toEqual(["quantum_flux", "done"]);
    expect(outcome).toBe("done");
  });
});

describe("streamChat global 401", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("returns 'unauthorized' and fires the global-401 notifier on a 401 response", async () => {
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 401 })) as typeof fetch;
    const heard = vi.fn();
    const off = onUnauthorized(heard);
    const outcome = await streamChat({ sessionId: null, message: "hi", acts: null }, () => {});
    off();
    expect(outcome).toBe("unauthorized");
    expect(heard).toHaveBeenCalledTimes(1);
  });
});

describe("streamChat abort", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async (_input, init) => {
      const encoder = new TextEncoder();
      const body = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('event: delta\ndata: {"text":"a"}\n\n'));
          init?.signal?.addEventListener("abort", () => {
            controller.error(new DOMException("aborted", "AbortError"));
          });
        },
      });
      return new Response(body, {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      });
    }) as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("aborts the read loop and reports network_error", async () => {
    const controller = new AbortController();
    const seen: string[] = [];
    const promise = streamChat(
      { sessionId: null, message: "hi", acts: null, signal: controller.signal },
      (ev) => {
        if (ev.event === "delta") seen.push(ev.data.text);
        controller.abort(); // abort right after the first frame
      },
    );
    const outcome = await promise;
    expect(seen).toEqual(["a"]);
    expect(outcome).toBe("network_error");
  });
});

describe("streamChat request body (E20)", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("передаёт template_slug из витрины и null без него", async () => {
    const bodies: unknown[] = [];
    globalThis.fetch = vi.fn(async (_input, init) => {
      bodies.push(JSON.parse(String(init?.body)));
      return new Response('event: done\ndata: {"message_id":"m1","stopped":false}\n\n', {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      });
    }) as typeof fetch;

    await streamChat(
      { sessionId: null, message: "Заполним шаблон", acts: null, templateSlug: "arenda" },
      () => {},
    );
    await streamChat({ sessionId: null, message: "обычный вопрос", acts: null }, () => {});

    expect((bodies[0] as { template_slug: string }).template_slug).toBe("arenda");
    expect((bodies[1] as { template_slug: null }).template_slug).toBeNull();
  });
});
