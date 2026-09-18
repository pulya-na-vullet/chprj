import { describe, expect, it } from "vitest";
import { authReducer, initialAuthState } from "../state/authReducer";

const user = { id: "u1", email: "a@b.ru", questions_asked: 0 };

describe("authReducer", () => {
  it("starts in the checking state with no user", () => {
    expect(initialAuthState).toEqual({ status: "checking", user: null, sessionExpired: false });
  });

  it("BOOT_AUTHENTICATED moves to authenticated with the user", () => {
    const s = authReducer(initialAuthState, { type: "BOOT_AUTHENTICATED", user });
    expect(s).toEqual({ status: "authenticated", user, sessionExpired: false });
  });

  it("BOOT_UNAUTHENTICATED moves to unauthenticated without a session-expired flag", () => {
    const s = authReducer(initialAuthState, { type: "BOOT_UNAUTHENTICATED" });
    expect(s).toEqual({ status: "unauthenticated", user: null, sessionExpired: false });
  });

  it("LOGIN_SUCCESS authenticates and clears any prior session-expired flag", () => {
    const expired = { status: "unauthenticated" as const, user: null, sessionExpired: true };
    const s = authReducer(expired, { type: "LOGIN_SUCCESS", user });
    expect(s).toEqual({ status: "authenticated", user, sessionExpired: false });
  });

  it("LOGGED_OUT clears the user and returns to unauthenticated", () => {
    const authed = { status: "authenticated" as const, user, sessionExpired: false };
    const s = authReducer(authed, { type: "LOGGED_OUT" });
    expect(s).toEqual({ status: "unauthenticated", user: null, sessionExpired: false });
  });

  it("SESSION_EXPIRED drops the user and sets the session-expired flag", () => {
    const authed = { status: "authenticated" as const, user, sessionExpired: false };
    const s = authReducer(authed, { type: "SESSION_EXPIRED" });
    expect(s).toEqual({ status: "unauthenticated", user: null, sessionExpired: true });
  });

  it("PROFILE_UPDATED заменяет пользователя, не трогая статус (T-0127)", () => {
    const authed = { status: "authenticated" as const, user, sessionExpired: false };
    const updated = { ...user, first_name: "Денис", onboarded_at: "2026-08-12T19:00:00Z" };
    const s = authReducer(authed, { type: "PROFILE_UPDATED", user: updated });
    expect(s).toEqual({ status: "authenticated", user: updated, sessionExpired: false });
  });
});
