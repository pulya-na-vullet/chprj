import { LogOut, PanelLeft, Plus } from "lucide-react";
import { useEffect } from "react";
import { useAuth } from "../state/AuthContext";
import { useChat } from "../state/ChatContext";
import { Button, IconButton, Tooltip } from "../ui";
import { AVATAR_PRESETS, initialsOf, presetBackground } from "../util/avatarPreset";
import { ConversationList } from "./ConversationList";
import { SidebarNav } from "./SidebarNav";
import { SidebarResizer } from "./SidebarResizer";
import { TourPill } from "./tour/TourPill";
import { useTourOptional } from "./tour/TourProvider";

function SidebarUser() {
  const { state, logout } = useAuth();
  if (!state.user) return null;
  const user = state.user;
  // T-0128: заполненный профиль — аватар-пресет с инициалами и имя;
  // пустой — прежний вид (буква + почта).
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
  const preset = user.avatar_preset ?? 0;
  const darkInk = (AVATAR_PRESETS[preset] ?? AVATAR_PRESETS[0]).ink === "dark";
  return (
    <div className="sidebar-user">
      {name ? (
        <span
          className={
            darkInk ? "sidebar-user-ava sidebar-user-preset dark-ink" : "sidebar-user-ava sidebar-user-preset"
          }
          // инлайн — вычисляемая генеративная отрисовка пресета, не косметика
          style={presetBackground(preset, "sm")}
          aria-hidden
        >
          {initialsOf(user.first_name, user.last_name)}
        </span>
      ) : (
        <span className="sidebar-user-ava" aria-hidden>
          {user.email[0].toUpperCase()}
        </span>
      )}
      <span className="sidebar-user-email" title={user.email}>
        {name || user.email}
      </span>
      <Tooltip content="Выйти">
        <IconButton icon={<LogOut size={16} />} onClick={() => void logout()} aria-label="Выйти" />
      </Tooltip>
    </div>
  );
}

// Пилюля тура (T-0132): центр сайдбара над блоком аккаунта; вне TourProvider
// (изолированные тесты Sidebar) просто не рендерится.
function SidebarTourPill({ collapsed }: { collapsed: boolean }) {
  const tour = useTourOptional();
  if (!tour) return null;
  return (
    <TourPill
      visible={tour.pillVisible}
      compact={collapsed}
      label={tour.pillText}
      celebrate={tour.celebrate}
      onStart={tour.start}
    />
  );
}

export function Sidebar() {
  const { state, newChat, toggleSidebar } = useChat();
  const collapsed = state.sidebarCollapsed;

  // Escape dismisses the mobile drawer only (desktop keeps the persistent rail).
  useEffect(() => {
    if (collapsed) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (window.matchMedia("(max-width: 760px)").matches) toggleSidebar();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [collapsed, toggleSidebar]);

  return (
    <>
      {!collapsed && <div className="sidebar-backdrop" onClick={toggleSidebar} aria-hidden="true" />}
      <aside
        className={collapsed ? "sidebar sidebar-collapsed" : "sidebar"}
        style={collapsed ? undefined : ({ ["--sidebar-w"]: `${state.sidebarWidth}px` } as React.CSSProperties)}
      >
        <div className="sidebar-head">
          <span className="sidebar-mark" aria-hidden="true" />
          <span className="brand">Нейроюрист</span>
          <IconButton
            className="sidebar-toggle"
            view="transparent"
            icon={<PanelLeft size={18} />}
            onClick={toggleSidebar}
            aria-label={collapsed ? "Развернуть" : "Свернуть"}
            aria-expanded={!collapsed}
          />
        </div>

        <Button
          className="new-chat"
          leftAddons={<Plus size={17} />}
          onClick={newChat}
          aria-label="Новая задача"
        >
          {!collapsed && <span className="sidebar-label">Новая задача</span>}
        </Button>

        {/* T-0053: разделы — сразу под «Новая задача» (замечание клиента:
            навигация была прижата к низу), история занимает остаток. */}
        <SidebarNav />

        <div className="sidebar-divider" />

        <ConversationList />

        <SidebarTourPill collapsed={collapsed} />

        <SidebarUser />

        {!collapsed && <SidebarResizer />}
      </aside>
    </>
  );
}
