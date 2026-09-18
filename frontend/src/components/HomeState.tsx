import { useAuth } from "../state/AuthContext";
import { useChat } from "../state/ChatContext";
import { Composer } from "./Composer";

/* «Сегодня» / «Вчера» / «2 июля» — короткая дата для поля реестра. */
function ledgerDate(iso: string, now: Date): string {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "";
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const today = day(now);
  if (t >= today) return "Сегодня";
  if (t >= today - 86_400_000) return "Вчера";
  return new Date(t).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

export function HomeState() {
  const { state, openConversation } = useChat();
  const { state: auth } = useAuth();
  const recent = state.conversations.slice(0, 3);
  const now = new Date();
  // T-0128: обращение по имени только при заполненном профиле.
  const firstName = auth.user?.first_name?.trim();

  return (
    <div className="home">
      <div className="home-hero">
        <header className="home-head">
          <h1 className="home-title">{firstName ? `${firstName}, с чего начнём?` : "С чего начнём?"}</h1>
          <p className="home-sub">Ответы по законодательству РФ со ссылками на статьи</p>
        </header>
        <Composer centered />
      </div>
      {recent.length > 0 && (
        <div className="home-ledger">
          <div className="home-ledger-h">Реестр задач</div>
          {recent.map((c) => (
            <button
              key={c.id}
              type="button"
              className="ledger-entry"
              onClick={() => void openConversation(c.id)}
            >
              <span className="ledger-date">{ledgerDate(c.updated_at, now)}</span>
              <span className="ledger-title">{c.title}</span>
              <span className="ledger-preview">{c.preview ?? "Без ответа"}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
