import type { LoginRequest, MeResponse, ProfileUpdateRequest, RegisterRequest } from "./types";

// Carries the backend's `detail` string (invalid_credentials / email_taken /
// rate_limited / …) so the UI can map it to a Russian message instead of
// showing a generic failure.
export class AuthApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "AuthApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function readDetail(resp: Response): Promise<string> {
  const payload: unknown = await resp.json().catch(() => null);
  const detail = (payload as { detail?: unknown } | null)?.detail;
  return typeof detail === "string" ? detail : `http_${resp.status}`;
}

async function postJson<TBody>(url: string, body: TBody): Promise<Response> {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new AuthApiError(resp.status, await readDetail(resp));
  return resp;
}

/** T-0026: register answers like login — MeResponse + immediate session cookie. */
export async function register(email: string, password: string): Promise<MeResponse> {
  const resp = await postJson<RegisterRequest>("/auth/register", { email, password });
  return (await resp.json()) as MeResponse;
}

export async function login(email: string, password: string): Promise<MeResponse> {
  const resp = await postJson<LoginRequest>("/auth/login", { email, password });
  return (await resp.json()) as MeResponse;
}

export async function logout(): Promise<void> {
  const resp = await fetch("/auth/logout", { method: "POST" });
  if (!resp.ok) throw new AuthApiError(resp.status, await readDetail(resp));
}

export async function getMe(): Promise<MeResponse> {
  const resp = await fetch("/auth/me", { headers: { Accept: "application/json" } });
  if (!resp.ok) throw new AuthApiError(resp.status, await readDetail(resp));
  return (await resp.json()) as MeResponse;
}

/** T-0127: частичное обновление профиля; onboarded: true ставит отметку
 * «онбординг показан» — сервер отвечает свежим MeResponse. */
export async function patchProfile(req: Partial<ProfileUpdateRequest>): Promise<MeResponse> {
  const resp = await fetch("/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) throw new AuthApiError(resp.status, await readDetail(resp));
  return (await resp.json()) as MeResponse;
}
