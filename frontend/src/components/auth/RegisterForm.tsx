import { useState } from "react";
import { passwordError, registerErrorMessage } from "../../api/authErrors";
import { useAuth } from "../../state/AuthContext";
import { Button, Input, PasswordInput } from "../../ui";

/** T-0026: a successful registration opens a session immediately —
 * AuthContext flips to authenticated and the shell replaces the auth
 * screens; there is no "письмо отправлено" screen anymore. */
export function RegisterForm({ onBackToLogin }: { onBackToLogin: () => void }) {
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    const pwError = passwordError(password);
    if (pwError) {
      setError(pwError);
      return;
    }
    setBusy(true);
    setError(null);
    register(email.trim(), password)
      .catch((err: unknown) => setError(registerErrorMessage(err)))
      .finally(() => setBusy(false));
  };

  return (
    <form className="auth-form" onSubmit={submit}>
      <h1 className="auth-title">Регистрация</h1>
      <Input
        label="Почта"
        type="email"
        required
        autoComplete="email"
        value={email}
        onChange={setEmail}
      />
      <PasswordInput
        label="Пароль"
        required
        autoComplete="new-password"
        hint="Не короче 8 символов"
        value={password}
        onChange={setPassword}
      />
      {error && (
        <div className="auth-error" role="alert">
          <span>{error}</span>
        </div>
      )}
      <Button type="submit" view="accent" size={48} loading={busy} disabled={busy} block>
        Зарегистрироваться
      </Button>
      <div className="auth-links">
        <button type="button" className="auth-link" onClick={onBackToLogin}>
          Уже есть аккаунт? Войти
        </button>
      </div>
    </form>
  );
}
