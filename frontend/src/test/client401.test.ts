import { afterEach, describe, expect, it, vi } from "vitest";
import { onUnauthorized } from "../api/authEvents";
import * as client from "../api/client";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

// Any protected-resource fetch answering 401 must fire the global-401
// notifier so the app can drop to the login screen, regardless of which
// client.ts function triggered it (GET-JSON path and raw-fetch path both
// need coverage since they're implemented separately).
describe("client.ts global 401", () => {
  it("listConversations (getJson path) notifies on 401", async () => {
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 401 })) as typeof fetch;
    const heard = vi.fn();
    const off = onUnauthorized(heard);
    await expect(client.listConversations()).rejects.toThrow();
    off();
    expect(heard).toHaveBeenCalledTimes(1);
  });

  it("deleteConversation (raw-fetch path) notifies on 401", async () => {
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 401 })) as typeof fetch;
    const heard = vi.fn();
    const off = onUnauthorized(heard);
    await expect(client.deleteConversation("c1")).rejects.toThrow();
    off();
    expect(heard).toHaveBeenCalledTimes(1);
  });

  it("does not notify on a normal 200", async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ conversations: [] }), { status: 200 }),
    ) as typeof fetch;
    const heard = vi.fn();
    const off = onUnauthorized(heard);
    await client.listConversations();
    off();
    expect(heard).not.toHaveBeenCalled();
  });
});
