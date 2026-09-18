import { useState } from "react";
import { loginErrorMessage } from "../../api/authErrors";
import { useAuth } from "../../state/AuthContext";
import { Button, Input, PasswordInput } from "../../ui";

export function LoginForm({
  sessionExpired,
  onRegister,
}: {
  sessionExpired: boolean;
  onRegister: () => void;
}) {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    login(email.trim(), password)
      .catch((err: unknown) => setError(loginErrorMessage(err)))
      .finally(() => setBusy(false));
  };

  return (
    <form className="auth-form" onSubmit={submit}>
      <h1 className="auth-title">Вход</h1>
      {sessionExpired && !error && <p className="auth-note">Сессия истекла — войдите снова.</p>}
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
        autoComplete="current-password"
        value={password}
        onChange={setPassword}
      />
      {error && (
        <div className="auth-error" role="alert">
          <span>{error}</span>
        </div>
      )}
      <Button type="submit" view="accent" size={48} loading={busy} disabled={busy} block>
        Войти
      </Button>
      <div className="auth-links">
        <button type="button" className="auth-link" onClick={onRegister}>
          Регистрация
        </button>
      </div>
    </form>
  );
}
