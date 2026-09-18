import { createContext, useCallback, useContext, useEffect, useMemo, useReducer } from "react";
import * as authApi from "../api/auth";
import { onUnauthorized } from "../api/authEvents";
import type { ProfileUpdateRequest } from "../api/types";
import { type AuthAction, type AuthState, authReducer, initialAuthState } from "./authReducer";

interface AuthContextValue {
  state: AuthState;
  /** Throws AuthApiError on failure — callers map `.detail` to UI copy. */
  login: (email: string, password: string) => Promise<void>;
  /** T-0026: registration opens a session immediately — same contract as login. */
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** T-0127: PATCH /profile; обновлённый MeResponse ложится в state.user —
   * после onboarded: true шелл сам уходит с онбординга на продукт. */
  saveProfile: (req: Partial<ProfileUpdateRequest>) => Promise<void>;
}

const Ctx = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(authReducer, initialAuthState);

  // Bootstrap: GET /auth/me once on mount. 200 → authenticated (shell
  // renders); 401 → unauthenticated (auth screens render instead).
  useEffect(() => {
    let alive = true;
    authApi
      .getMe()
      .then((user) => {
        if (alive) dispatch({ type: "BOOT_AUTHENTICATED", user });
      })
      .catch(() => {
        if (alive) dispatch({ type: "BOOT_UNAUTHENTICATED" });
      });
    return () => {
      alive = false;
    };
  }, []);

  // Global 401: any protected-resource fetch (client.ts, sse.ts) reports
  // here via the shared notifier — drop straight to "session expired"
  // regardless of which call site saw the 401.
  useEffect(
    () =>
      onUnauthorized(() => {
        const expired: AuthAction = { type: "SESSION_EXPIRED" };
        dispatch(expired);
      }),
    [],
  );

  const login = useCallback(async (email: string, password: string) => {
    const user = await authApi.login(email, password);
    dispatch({ type: "LOGIN_SUCCESS", user });
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const user = await authApi.register(email, password);
    dispatch({ type: "LOGIN_SUCCESS", user });
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      dispatch({ type: "LOGGED_OUT" });
    }
  }, []);

  const saveProfile = useCallback(async (req: Partial<ProfileUpdateRequest>) => {
    const user = await authApi.patchProfile(req);
    dispatch({ type: "PROFILE_UPDATED", user });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ state, login, register, logout, saveProfile }),
    [state, login, register, logout, saveProfile],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
