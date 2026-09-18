// Провайдер тура (T-0132, спека E19 §9): автозапуск на Home при
// tour_completed_at IS NULL, перезапуск с пилюли, финал с автонабором
// вопроса в композер и пульсом кнопки отправки. «Пропустить» и финал ставят
// отметку через PATCH /profile (идемпотентно на бэке).
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import { useAuth } from "../../state/AuthContext";
import { useChat } from "../../state/ChatContext";
import {
  TOUR_FINALE_QUESTION,
  initialTourState,
  isPillVisible,
  pillLabel,
  tourReducer,
  type TourState,
} from "../../tour/tourMachine";
import { prefersReducedMotion } from "../../util/motion";
import { TourOverlay } from "./TourOverlay";

const CELEBRATE_MS = 3400; // искра 1.6с × 2 оборота + небольшой хвост
const FADE_MS = 550; // растворение затемнения перед автонабором
const TYPE_TICK_MS = 32;
const AUTOSTART_DELAY_MS = 800;

interface TourContextValue {
  state: TourState;
  pillVisible: boolean;
  pillText: string;
  celebrate: boolean;
  start: () => void;
  next: () => void;
  skip: () => void;
}

const Ctx = createContext<TourContextValue | null>(null);

function seenStorageKey(userId: string): string {
  return `neurolegal.tour.seen.${userId}`;
}

function loadSeen(userId: string): number {
  try {
    const raw = window.localStorage.getItem(seenStorageKey(userId));
    const n = raw === null ? 0 : Number.parseInt(raw, 10);
    return Number.isFinite(n) && n > 0 ? Math.min(n, 4) : 0;
  } catch {
    return 0;
  }
}

export function TourProvider({ children }: { children: React.ReactNode }) {
  const { state: auth, saveProfile } = useAuth();
  const chat = useChat();
  const userId = auth.user?.id ?? "";
  const [state, dispatch] = useReducer(
    tourReducer,
    initialTourState,
    (init): TourState => ({ ...init, maxSeen: userId ? loadSeen(userId) : 0 }),
  );
  const [celebrate, setCelebrate] = useState(false);
  const timers = useRef<number[]>([]);
  const autostarted = useRef(false);

  const clearTimers = () => {
    for (const t of timers.current) window.clearTimeout(t);
    timers.current = [];
  };
  useEffect(() => clearTimers, []);

  // Счётчик пилюли переживает перезагрузку (максимум пройденного).
  useEffect(() => {
    if (!userId || state.maxSeen === 0) return;
    try {
      window.localStorage.setItem(seenStorageKey(userId), String(state.maxSeen));
    } catch {
      // приватный режим — счётчик просто не переживёт перезагрузку
    }
  }, [userId, state.maxSeen]);

  const markCompleted = useCallback(() => {
    // Идемпотентно на бэке; при уже стоящей отметке не дёргаем сеть.
    if (auth.user?.tour_completed_at != null) return;
    saveProfile({ tour_completed: true }).catch(() => {
      // Не удалось сохранить отметку — тур не ломаем; при следующем заходе
      // автозапуск повторится, что честно отражает состояние сервера.
    });
  }, [auth.user?.tour_completed_at, saveProfile]);

  const start = useCallback(() => {
    clearTimers();
    chat.setComposerPulse(false);
    // Свёрнутый сайдбар тур предварительно разворачивает — якоря «Файлы» и
    // «Проверки» должны быть видны в полной форме (критерий приёмки).
    if (chat.state.sidebarCollapsed) chat.toggleSidebar();
    dispatch({ type: "START" });
  }, [chat]);

  const skip = useCallback(() => {
    clearTimers();
    dispatch({ type: "SKIP" });
    markCompleted();
  }, [markCompleted]);

  const runFinale = useCallback(
    (quiet: boolean) => {
      markCompleted();
      setCelebrate(true);
      timers.current.push(window.setTimeout(() => setCelebrate(false), CELEBRATE_MS));
      // Повторное прохождение (перезапуск с пилюли при уже стоящей отметке):
      // просто ещё раз показываем шаги — без автонабора вопроса и пульса.
      if (quiet) return;
      const reduceMotion = prefersReducedMotion();
      timers.current.push(
        window.setTimeout(() => {
          if (reduceMotion) {
            // Без тайпрайтера: вопрос появляется целиком, пульс отключён CSS.
            chat.prefillComposer(TOUR_FINALE_QUESTION);
            chat.setComposerPulse(true);
            return;
          }
          let i = 1;
          const type = () => {
            chat.prefillComposer(TOUR_FINALE_QUESTION.slice(0, i));
            if (i < TOUR_FINALE_QUESTION.length) {
              i += 1;
              timers.current.push(window.setTimeout(type, TYPE_TICK_MS));
            } else {
              chat.setComposerPulse(true);
            }
          };
          timers.current.push(window.setTimeout(type, 250));
        }, FADE_MS),
      );
    },
    [chat, markCompleted],
  );

  const next = useCallback(() => {
    const last = state.status === "steps" && state.step === 3;
    // «Тихий» финал, если отметка уже стояла на момент завершения — значит,
    // это повторный прогон, автонабор и подсветка отправки не нужны.
    const alreadyCompleted = auth.user?.tour_completed_at != null;
    dispatch({ type: "NEXT" });
    if (last) runFinale(alreadyCompleted);
  }, [state.status, state.step, auth.user?.tour_completed_at, runFinale]);

  // Автозапуск: один раз за сессию, на Home, только пока отметки нет.
  useEffect(() => {
    if (autostarted.current) return;
    if (auth.user == null || auth.user.tour_completed_at != null) return;
    if (chat.state.view !== "chat" || chat.state.currentId !== null) return;
    autostarted.current = true;
    const t = window.setTimeout(start, AUTOSTART_DELAY_MS);
    timers.current.push(t);
  }, [auth.user, chat.state.view, chat.state.currentId, start]);

  const questionsAsked =
    (auth.user?.questions_asked ?? 0) + chat.state.questionsSentInSession;
  // Порог «3 вопроса» прячет пилюлю в покое, но не во время активного тура
  // и не в момент искры финала — иначе завершение тура нечем отметить.
  const tourOnScreen = state.status === "steps" || state.status === "finale";

  const value = useMemo<TourContextValue>(
    () => ({
      state,
      pillVisible: tourOnScreen || celebrate || isPillVisible(questionsAsked),
      pillText: pillLabel(state.maxSeen),
      celebrate,
      start,
      next,
      skip,
    }),
    [state, tourOnScreen, questionsAsked, celebrate, start, next, skip],
  );

  return (
    <Ctx.Provider value={value}>
      {children}
      <TourOverlay />
    </Ctx.Provider>
  );
}

export function useTour(): TourContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useTour outside TourProvider");
  return v;
}

/** Для мест, которые рендерятся и без тура (Sidebar в тестах): нет
 * провайдера — нет пилюли, ошибки тоже нет. */
export function useTourOptional(): TourContextValue | null {
  return useContext(Ctx);
}
