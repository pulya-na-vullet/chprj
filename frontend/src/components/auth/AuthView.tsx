import { useState } from "react";
import { useAuth } from "../../state/AuthContext";
import { AuthCard } from "./AuthCard";
import { LoginForm } from "./LoginForm";
import { RegisterForm } from "./RegisterForm";

/** Rendered whenever `AuthContext` says there's no session. Two screens only
 * (T-0026 — no mail flows): login and register; individual forms own their
 * own field state. */
export function AuthView() {
  const { state } = useAuth();
  const [screen, setScreen] = useState<"login" | "register">("login");

  return (
    <AuthCard>
      {screen === "login" && (
        <LoginForm
          sessionExpired={state.sessionExpired}
          onRegister={() => setScreen("register")}
        />
      )}
      {screen === "register" && <RegisterForm onBackToLogin={() => setScreen("login")} />}
    </AuthCard>
  );
}
