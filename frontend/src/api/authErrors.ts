import { AuthApiError } from "./auth";

export const MIN_PASSWORD_LENGTH = 8;

/** Client-side pre-check mirroring the backend's minimum (contracts/auth.py). */
export function passwordError(password: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Пароль должен быть не короче ${MIN_PASSWORD_LENGTH} символов`;
  }
  return null;
}

/** Maps `/auth/login` failures (routes.py: 401/429) to UI copy. */
export function loginErrorMessage(err: unknown): string {
  if (err instanceof AuthApiError) {
    if (err.detail === "invalid_credentials") return "Неверная почта или пароль";
    if (err.detail === "rate_limited")
      return "Слишком много попыток. Подождите несколько минут.";
  }
  return "Не удалось войти. Попробуйте ещё раз.";
}

/** Maps `/auth/register` failures (routes.py: 409 email_taken / 429) to UI copy. */
export function registerErrorMessage(err: unknown): string {
  if (err instanceof AuthApiError) {
    if (err.detail === "email_taken") return "Такая почта уже зарегистрирована — войдите";
    if (err.detail === "rate_limited")
      return "Слишком много попыток. Подождите несколько минут.";
  }
  return "Не удалось зарегистрироваться. Попробуйте ещё раз.";
}
