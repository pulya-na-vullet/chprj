import { describe, expect, it } from "vitest";
import { AuthApiError } from "../api/auth";
import {
  MIN_PASSWORD_LENGTH,
  loginErrorMessage,
  passwordError,
  registerErrorMessage,
} from "../api/authErrors";

describe("loginErrorMessage", () => {
  it("maps invalid_credentials", () => {
    expect(loginErrorMessage(new AuthApiError(401, "invalid_credentials"))).toBe(
      "Неверная почта или пароль",
    );
  });

  it("maps rate_limited", () => {
    expect(loginErrorMessage(new AuthApiError(429, "rate_limited"))).toMatch(/попыток/i);
  });

  it("falls back to a generic message for unrecognized errors", () => {
    expect(loginErrorMessage(new Error("boom")).length).toBeGreaterThan(0);
  });
});

describe("registerErrorMessage", () => {
  it("maps email_taken", () => {
    expect(registerErrorMessage(new AuthApiError(409, "email_taken"))).toMatch(
      /уже зарегистрирован/i,
    );
  });

  it("maps rate_limited", () => {
    expect(registerErrorMessage(new AuthApiError(429, "rate_limited"))).toMatch(/попыток/i);
  });

  it("falls back to a generic message otherwise", () => {
    expect(registerErrorMessage(new Error("boom")).length).toBeGreaterThan(0);
  });
});

describe("passwordError", () => {
  it("rejects passwords shorter than the minimum", () => {
    expect(passwordError("a".repeat(MIN_PASSWORD_LENGTH - 1))).not.toBeNull();
  });

  it("accepts passwords at or above the minimum", () => {
    expect(passwordError("a".repeat(MIN_PASSWORD_LENGTH))).toBeNull();
  });
});
