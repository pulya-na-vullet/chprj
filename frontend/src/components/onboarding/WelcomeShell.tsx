// Общая оболочка пути «регистрация → онбординг» (T-0127/T-0129, спека E19
// §2–3): белая страница, лого сверху, карточка 50/50 с превью продукта
// справа, футер. Левую половину наполняет вызывающий экран.
export function WelcomeShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="ob-page">
      <div className="ob-brand">
        <span className="ob-mark" aria-hidden="true" />
        <span className="ob-brand-name">Нейроюрист</span>
      </div>

      <div className="ob-card">
        <div className="ob-pane-form">{children}</div>
        <div className="ob-pane-right" aria-hidden="true">
          <img src="/onboarding-home.png" alt="" />
        </div>
      </div>

      <div className="ob-foot">
        <span>© 2026 Нейроюрист</span>
        <span>Конфиденциальность</span>
        <span>Поддержка</span>
      </div>
    </div>
  );
}
