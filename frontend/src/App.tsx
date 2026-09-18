import { Suspense, lazy } from "react";
import { AuthView } from "./components/auth/AuthView";
import { ChatPane } from "./components/ChatPane";
import { Sidebar } from "./components/Sidebar";
import { TourProvider } from "./components/tour/TourProvider";
import { AuthProvider, useAuth } from "./state/AuthContext";
import { ChatProvider, useChat } from "./state/ChatContext";

// Чат — экран по умолчанию и якорь тура, он в основном бандле. Остальные
// разделы грузятся при первом заходе: до 708 KB одним куском доходило
// каждому, кто просто задал вопрос (T-0143). Онбординг тоже отдельным
// куском — он показывается ровно один раз за жизнь аккаунта.
const FilesView = lazy(() =>
  import("./components/files/FilesView").then((m) => ({ default: m.FilesView })),
);
const ReviewsView = lazy(() =>
  import("./components/reviews/ReviewsView").then((m) => ({ default: m.ReviewsView })),
);
const SourcesView = lazy(() =>
  import("./components/sources/SourcesView").then((m) => ({ default: m.SourcesView })),
);
const TemplatesView = lazy(() =>
  import("./components/templates/TemplatesView").then((m) => ({ default: m.TemplatesView })),
);
const OnboardingView = lazy(() =>
  import("./components/onboarding/OnboardingView").then((m) => ({ default: m.OnboardingView })),
);

/** Тот же текстовый приём, что и у самих разделов («Загрузка…») — на время
 * догрузки куска, обычно доли секунды. */
function ViewFallback() {
  return <div className="boot-loading">Загрузка…</div>;
}

function AppShell() {
  const { state } = useChat();
  return (
    <div className="app">
      <Sidebar />
      {state.view === "chat" ? (
        <ChatPane />
      ) : (
        <Suspense fallback={<ViewFallback />}>
          {state.view === "sources" ? (
            <SourcesView />
          ) : state.view === "reviews" ? (
            <ReviewsView />
          ) : state.view === "templates" ? (
            <TemplatesView />
          ) : (
            <FilesView />
          )}
        </Suspense>
      )}
    </div>
  );
}

// Bootstraps on GET /auth/me (via AuthProvider): "checking" reuses the
// existing plain-text loading pattern (see FilesView/SourcesView's
// "Загрузка…") instead of a new splash. Only once a session is confirmed
// does ChatProvider mount — so an unauthenticated visitor never fires the
// chat/conversations/acts requests that would otherwise all fail with 401.
function Root() {
  const { state } = useAuth();
  if (state.status === "checking") {
    return <div className="boot-loading">Загрузка…</div>;
  }
  if (state.status === "unauthenticated") {
    return <AuthView />;
  }
  // T-0127: онбординг вместо продукта, пока onboarded_at IS NULL. ChatProvider
  // не монтируется — chat/conversations/acts не дёргаются до входа в продукт.
  if (state.user && state.user.onboarded_at == null) {
    return (
      <Suspense fallback={<ViewFallback />}>
        <OnboardingView />
      </Suspense>
    );
  }
  return (
    <ChatProvider>
      {/* T-0132: тур живёт под ChatProvider (композер, сайдбар) и поверх
          продукта; автозапуск — при tour_completed_at IS NULL. */}
      <TourProvider>
        <AppShell />
      </TourProvider>
    </ChatProvider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Root />
    </AuthProvider>
  );
}
