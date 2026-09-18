import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthApiError, getMe, login, logout, register } from "../api/auth";

const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("register", () => {
  it("posts email+password and resolves with the MeResponse (immediate session)", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { id: "u1", email: "a@b.ru" }));
    globalThis.fetch = fetchMock as typeof fetch;
    await expect(register("a@b.ru", "password1")).resolves.toEqual({ id: "u1", email: "a@b.ru" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/auth/register",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "a@b.ru", password: "password1" }),
      }),
    );
  });

  it("surfaces email_taken (409) as an AuthApiError", async () => {
    globalThis.fetch = vi.fn(async () => jsonResponse(409, { detail: "email_taken" })) as typeof fetch;
    await expect(register("a@b.ru", "password1")).rejects.toMatchObject({
      status: 409,
      detail: "email_taken",
    });
  });

  it("throws AuthApiError carrying the detail code on failure", async () => {
    globalThis.fetch = vi.fn(async () => jsonResponse(429, { detail: "rate_limited" })) as typeof fetch;
    await expect(register("a@b.ru", "password1")).rejects.toMatchObject({
      status: 429,
      detail: "rate_limited",
    });
  });
});

describe("login", () => {
  it("resolves with the MeResponse on success", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse(200, { id: "u1", email: "a@b.ru" }),
    ) as typeof fetch;
    await expect(login("a@b.ru", "password1")).resolves.toEqual({ id: "u1", email: "a@b.ru" });
  });

  it("surfaces invalid_credentials as an AuthApiError", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse(401, { detail: "invalid_credentials" }),
    ) as typeof fetch;
    await expect(login("a@b.ru", "wrong")).rejects.toBeInstanceOf(AuthApiError);
    globalThis.fetch = vi.fn(async () =>
      jsonResponse(401, { detail: "invalid_credentials" }),
    ) as typeof fetch;
    await expect(login("a@b.ru", "wrong")).rejects.toMatchObject({
      status: 401,
      detail: "invalid_credentials",
    });
  });
});

describe("getMe", () => {
  it("resolves with the current user on 200", async () => {
    globalThis.fetch = vi.fn(async () =>
      jsonResponse(200, { id: "u1", email: "a@b.ru" }),
    ) as typeof fetch;
    await expect(getMe()).resolves.toEqual({ id: "u1", email: "a@b.ru" });
  });

  it("throws AuthApiError(401) when there is no session", async () => {
    globalThis.fetch = vi.fn(async () => jsonResponse(401, { detail: "not_authenticated" })) as typeof fetch;
    await expect(getMe()).rejects.toMatchObject({ status: 401 });
  });
});

describe("logout", () => {
  it("resolves on 204 No Content", async () => {
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 204 })) as typeof fetch;
    await expect(logout()).resolves.toBeUndefined();
  });
});
