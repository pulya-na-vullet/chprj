import { WelcomeShell } from "../onboarding/WelcomeShell";

/** Оболочка auth-экранов (T-0129): та же композиция, что у онбординга —
 * общий WelcomeShell (лого, карточка 50/50 с превью продукта, футер),
 * форма по центру левой половины. Единый путь регистрация → онбординг
 * без визуального шва. */
export function AuthCard({ children }: { children: React.ReactNode }) {
  return (
    <WelcomeShell>
      <div className="auth-center">{children}</div>
    </WelcomeShell>
  );
}
