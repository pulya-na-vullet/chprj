import { FileText, LayoutGrid, Scale, SquareCheckBig } from "lucide-react";
import type { ChatView } from "../state/chatReducer";
import { useChat } from "../state/ChatContext";

export function SidebarNav() {
  const { state, setView } = useChat();

  // dataTour — DOM-якорь шага тура (T-0132); вырез снимает геометрию с кнопки.
  // aria-label дублирует видимую подпись: в свёрнутом сайдбаре (и на узких
  // экранах) CSS прячет <span>, и без него у кнопки не остаётся имени —
  // скринридер читал бы четыре безымянные кнопки (T-0143).
  const item = (view: ChatView, label: string, Icon: typeof Scale, dataTour?: string) => (
    <button
      type="button"
      className={state.view === view ? "nav-item nav-item-active" : "nav-item"}
      data-tour={dataTour}
      aria-label={label}
      aria-current={state.view === view ? "page" : undefined}
      onClick={() => setView(view)}
    >
      <Icon size={18} />
      <span>{label}</span>
    </button>
  );

  return (
    <nav className="sidebar-nav">
      {item("sources", "Источники права", Scale)}
      {item("reviews", "Проверки", SquareCheckBig, "reviews")}
      {item("files", "Файлы", FileText, "files")}
      {item("templates", "Шаблоны", LayoutGrid)}
    </nav>
  );
}
