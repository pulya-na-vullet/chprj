// Global session state: who's logged in (if anyone), and whether the SPA
// just got kicked back to the login screen by an expired/invalidated
// session (vs. a plain first-load "never logged in").

import type { MeResponse } from "../api/types";

// Полная форма MeResponse (T-0127): помимо id/email несёт профильные поля —
// шелл решает по onboarded_at, показывать ли онбординг вместо продукта.
export type AuthUser = MeResponse;

export type AuthStatus = "checking" | "authenticated" | "unauthenticated";

export interface AuthState {
  status: AuthStatus;
  user: AuthUser | null;
  sessionExpired: boolean;
}

export const initialAuthState: AuthState = {
  status: "checking",
  user: null,
  sessionExpired: false,
};

export type AuthAction =
  | { type: "BOOT_AUTHENTICATED"; user: AuthUser }
  | { type: "BOOT_UNAUTHENTICATED" }
  | { type: "LOGIN_SUCCESS"; user: AuthUser }
  | { type: "PROFILE_UPDATED"; user: AuthUser }
  | { type: "LOGGED_OUT" }
  | { type: "SESSION_EXPIRED" };

export function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case "BOOT_AUTHENTICATED":
      return { status: "authenticated", user: action.user, sessionExpired: false };
    case "BOOT_UNAUTHENTICATED":
      return { status: "unauthenticated", user: null, sessionExpired: false };
    case "LOGIN_SUCCESS":
      return { status: "authenticated", user: action.user, sessionExpired: false };
    case "PROFILE_UPDATED":
      // Ответ PATCH /profile — свежий MeResponse; статус сессии не меняется.
      return { ...state, user: action.user };
    case "LOGGED_OUT":
      return { status: "unauthenticated", user: null, sessionExpired: false };
    case "SESSION_EXPIRED":
      return { status: "unauthenticated", user: null, sessionExpired: true };
  }
}
