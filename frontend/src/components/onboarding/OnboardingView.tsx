// Экран профиль-онбординга (T-0127, спека E19 §3, эталон flow-full.html):
// два шага + финал-анимация полосы прогресса (заливка → круг → центр ×2 →
// штрих-галочка). Показывается вместо продукта при onboarded_at IS NULL;
// сохранение одним PATCH /profile в момент выхода («Начать работу»).
import { useEffect, useMemo, useRef, useState } from "react";
import type { ProfileUpdateRequest } from "../../api/types";
import { useAuth } from "../../state/AuthContext";
import { Button, Input } from "../../ui";
import { AVATAR_PRESETS, initialsOf, presetBackground } from "../../util/avatarPreset";
import { prefersReducedMotion } from "../../util/motion";
import { WelcomeShell } from "./WelcomeShell";

type UsageKind = "personal" | "business";
type RoleKey = "lawyer" | "accountant" | "manager" | "other";
type TaskKey = "law_questions" | "contract_review" | "drafting" | "files";

const ROLES: ReadonlyArray<{ key: RoleKey; label: string }> = [
  { key: "lawyer", label: "Юрист" },
  { key: "accountant", label: "Бухгалтер" },
  { key: "manager", label: "Руководитель" },
  { key: "other", label: "Другое" },
];

// Ключи задач одинаковы для обеих веток — различаются только надписи (§4).
const TASKS: Record<UsageKind, ReadonlyArray<{ key: TaskKey; title: string; desc: string }>> = {
  business: [
    { key: "law_questions", title: "Вопросы по законодательству", desc: "Ответы по кодексам со ссылками на статьи" },
    { key: "contract_review", title: "Проверка договоров", desc: "Риски и слабые места со ссылками на нормы" },
    { key: "drafting", title: "Составление документов", desc: "Претензии, ответы контрагентам, формулировки" },
    { key: "files", title: "Работа со своими файлами", desc: "Библиотека договоров: чтение, поиск, разбор" },
  ],
  personal: [
    { key: "law_questions", title: "Вопросы по законам", desc: "Права, обязанности и сроки — простым языком" },
    { key: "contract_review", title: "Проверка договоров", desc: "Аренда, кредит, покупка: что вы подписываете" },
    { key: "drafting", title: "Составление документов", desc: "Претензии, заявления, жалобы" },
    { key: "files", title: "Работа со своими файлами", desc: "Загрузите документ — разберём и объясним" },
  ],
};

// Тайминги финала — из принятого прототипа (спека §3.2).
const FINALE_CIRCLE_MS = 600;
const FINALE_CENTER_MS = 1150;
const FINALE_DRAWN_MS = 1750;
const FINALE_ON_MS = 2050;
const FINALE_BACK_MS = 620;

export interface ProfileDraft {
  skipped: boolean;
  firstName: string;
  lastName: string;
  preset: number;
  usageKind: UsageKind;
  role: RoleKey | null;
  tasks: TaskKey[];
}

/** Сборка PATCH-запроса из черновика (§3.6): пропуск шлёт только onboarded;
 * пустые имя/фамилия не отправляются; роль — только в ветке бизнеса. */
export function buildProfileRequest(draft: ProfileDraft): Partial<ProfileUpdateRequest> {
  if (draft.skipped) return { onboarded: true };
  const req: Partial<ProfileUpdateRequest> = {
    avatar_preset: draft.preset,
    usage_kind: draft.usageKind,
    onboarded: true,
  };
  const first = draft.firstName.trim();
  const last = draft.lastName.trim();
  if (first) req.first_name = first;
  if (last) req.last_name = last;
  if (draft.usageKind === "business" && draft.role) req.role = draft.role;
  if (draft.tasks.length > 0) req.tasks = draft.tasks;
  return req;
}

type FinaleState = { skipped: boolean } | null;
// Фазы анимации финала: fill → circle → center → drawn → on (тексты).
type FinalePhase = "fill" | "circle" | "center" | "drawn" | "on";

export function OnboardingScreen({
  email,
  onSave,
}: {
  email: string;
  onSave: (req: Partial<ProfileUpdateRequest>) => Promise<void>;
}) {
  const [step, setStep] = useState<1 | 2>(1);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [preset, setPreset] = useState(0);
  const [usageKind, setUsageKind] = useState<UsageKind>("personal");
  const [role, setRole] = useState<RoleKey | null>(null);
  const [tasks, setTasks] = useState<TaskKey[]>([]);
  const [finale, setFinale] = useState<FinaleState>(null);
  const [phase, setPhase] = useState<FinalePhase>("fill");
  const [closing, setClosing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trackRef = useRef<HTMLDivElement | null>(null);
  const spotRef = useRef<HTMLDivElement | null>(null);
  const timers = useRef<number[]>([]);

  // Инлайн-стили аватара — вычисляемая генеративная отрисовка пресета
  // (детерминированная функция, спека §3.3), не косметика.
  const avatarStyle = useMemo(() => presetBackground(preset, "lg"), [preset]);
  const initials = initialsOf(firstName, lastName);

  const clearTimers = () => {
    for (const t of timers.current) window.clearTimeout(t);
    timers.current = [];
  };
  useEffect(() => clearTimers, []);

  const runFinale = (skipped: boolean) => {
    setFinale({ skipped });
    setClosing(false);
    // Морф полосы в галочку выключен системной настройкой — цепочка фаз
    // осталась бы двумя секундами ожидания пустого экрана перед «Начать
    // работу» (T-0143). Показываем финал сразу.
    if (prefersReducedMotion()) {
      setPhase("on");
      return;
    }
    setPhase("fill");
    timers.current = [
      window.setTimeout(() => setPhase("circle"), FINALE_CIRCLE_MS),
      window.setTimeout(() => setPhase("center"), FINALE_CENTER_MS),
      window.setTimeout(() => setPhase("drawn"), FINALE_DRAWN_MS),
      window.setTimeout(() => setPhase("on"), FINALE_ON_MS),
    ];
  };

  const backFromFinale = () => {
    clearTimers();
    setClosing(true);
    setPhase("fill");
    if (prefersReducedMotion()) {
      setFinale(null);
      setClosing(false);
      setStep(2);
      return;
    }
    timers.current = [
      window.setTimeout(() => {
        setFinale(null);
        setClosing(false);
        setStep(2);
      }, FINALE_BACK_MS),
    ];
  };

  // Круг едет в центр правой середины панели: геометрия считается по
  // фактическим ректам (как в прототипе), масштаб ×2 → 96px.
  const trackTransform = useMemo(() => {
    if (!finale || closing || (phase !== "center" && phase !== "drawn" && phase !== "on")) {
      return undefined;
    }
    const track = trackRef.current?.getBoundingClientRect();
    const spot = spotRef.current?.getBoundingClientRect();
    if (!track || !spot) return undefined;
    const dy = spot.top + spot.height / 2 - (track.top + track.height / 2);
    return `translateY(${dy}px) scale(2)`;
  }, [finale, closing, phase]);

  const switchKind = (kind: UsageKind) => {
    if (kind === usageKind) return;
    setUsageKind(kind);
    // Как в прототипе: наборы меняются целиком, выбор сбрасывается.
    setRole(null);
    setTasks([]);
  };

  const toggleTask = (key: TaskKey) => {
    setTasks((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  };

  const startWork = () => {
    if (busy || !finale) return;
    setBusy(true);
    setError(null);
    const draft: ProfileDraft = {
      skipped: finale.skipped,
      firstName,
      lastName,
      preset,
      usageKind,
      role,
      tasks,
    };
    onSave(buildProfileRequest(draft)).catch(() => {
      setError("Не удалось сохранить — попробуйте ещё раз.");
      setBusy(false);
    });
  };

  const trimmedFirst = firstName.trim();
  const finTitle = trimmedFirst ? `Готово, ${trimmedFirst}` : "Готово";
  const finSub = finale?.skipped
    ? "Профиль можно заполнить позже — в любой момент в настройках."
    : "Профиль сохранён — ответы настроены под ваши задачи.";

  const circleOn = finale !== null && !closing && phase !== "fill";
  const drawnOn = finale !== null && !closing && (phase === "drawn" || phase === "on");
  // Прогресс заливки — сдвиг полноширинного слоя (transform, не width):
  // -100% = 0%, -50% = 50%, 0 = 100%.
  const fillShift = finale !== null ? (closing ? "-50%" : "0%") : step === 1 ? "-100%" : "-50%";

  return (
    <WelcomeShell>
      <div className={finale ? "ob-bar fin" : "ob-bar"}>
            <div className="ob-bar-labels">
              <div className="ob-bar-labels-row">
                <span className={step === 1 ? "on" : undefined}>Шаг 1</span>
                <span className={step === 2 ? "on" : undefined}>Шаг 2</span>
              </div>
            </div>
            <div
              ref={trackRef}
              className={`ob-track${circleOn ? " circle" : ""}${drawnOn ? " drawn" : ""}`}
              style={trackTransform ? { transform: trackTransform } : undefined}
            >
              <div className="ob-fill" style={{ transform: `translateX(${fillShift})` }} />
              <svg className="ob-chk" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  d="M5.5 12.5l4.2 4.2L18.5 7.5"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
          </div>

          {/* Шаг 1 «Давайте познакомимся» */}
          <div className="ob-step" hidden={step !== 1 || finale !== null}>
            <h1 className="ob-title">Давайте познакомимся</h1>
            <div className="ob-ava-cap">Аватар</div>
            <div className="ob-ava-row">
              <div
                className={AVATAR_PRESETS[preset].ink === "dark" ? "ob-ava dark-ink" : "ob-ava"}
                style={avatarStyle}
                data-testid="ob-avatar"
              >
                {initials}
              </div>
              <div className="ob-swatches" role="radiogroup" aria-label="Аватар">
                {AVATAR_PRESETS.map((_p, i) => (
                  <button
                    key={i}
                    type="button"
                    role="radio"
                    aria-checked={preset === i}
                    aria-label={`Пресет ${i + 1}`}
                    className={preset === i ? "ob-sw on" : "ob-sw"}
                    style={presetBackground(i, "sm")}
                    onClick={() => setPreset(i)}
                  />
                ))}
              </div>
            </div>
            <div className="ob-fields">
              <Input
                label="Имя"
                placeholder="Введите имя"
                value={firstName}
                onChange={setFirstName}
                autoComplete="given-name"
              />
              <Input
                label="Фамилия"
                placeholder="Введите фамилию"
                value={lastName}
                onChange={setLastName}
                autoComplete="family-name"
              />
              <Input label="Почта" value={email} disabled />
            </div>
            <div className="ob-grow" />
            <Button view="accent" size={48} block onClick={() => setStep(2)}>
              Продолжить
            </Button>
            <div className="ob-links">
              <button type="button" className="ob-link" onClick={() => runFinale(true)}>
                Заполнить позже
              </button>
            </div>
          </div>

          {/* Шаг 2 «Пара слов о ваших задачах» */}
          <div className="ob-step" hidden={step !== 2 || finale !== null}>
            <h1 className="ob-title">Пара слов о ваших задачах</h1>
            {/* aria-pressed — как у чипов роли ниже: состояние сегмента
                нельзя оставлять только на цвете подложки. */}
            <div className="ob-segm">
              <button
                type="button"
                aria-pressed={usageKind === "personal"}
                className={usageKind === "personal" ? "on" : undefined}
                onClick={() => switchKind("personal")}
              >
                Для себя
              </button>
              <button
                type="button"
                aria-pressed={usageKind === "business"}
                className={usageKind === "business" ? "on" : undefined}
                onClick={() => switchKind("business")}
              >
                Для бизнеса
              </button>
            </div>
            {usageKind === "business" && (
              <div key="role">
                <p className="ob-sect">Ваша роль</p>
                <div className="ob-chips">
                  {ROLES.map((r, i) => (
                    <button
                      key={r.key}
                      type="button"
                      aria-pressed={role === r.key}
                      className={role === r.key ? "ob-chip anim on" : "ob-chip anim"}
                      style={{ animationDelay: `${i * 50}ms` }}
                      onClick={() => setRole(r.key)}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <p className="ob-sect">Что будете делать чаще всего — можно несколько</p>
            {/* key=usageKind перезапускает стаггер при переключении сегмента */}
            <div className="ob-taskrows" key={usageKind}>
              {TASKS[usageKind].map((t, i) => (
                <button
                  key={t.key}
                  type="button"
                  aria-pressed={tasks.includes(t.key)}
                  className={tasks.includes(t.key) ? "ob-trow anim on" : "ob-trow anim"}
                  style={{ animationDelay: `${(usageKind === "business" ? 250 : 40) + i * 70}ms` }}
                  onClick={() => toggleTask(t.key)}
                >
                  <span className="ob-trow-tx">
                    <b>{t.title}</b>
                    <span>{t.desc}</span>
                  </span>
                  <span className="ob-tick" aria-hidden="true">
                    <svg viewBox="0 0 12 12" fill="none">
                      <path
                        d="M2.2 6.4l2.6 2.6 5-6"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </span>
                </button>
              ))}
            </div>
            <div className="ob-grow" />
            <Button view="accent" size={48} block onClick={() => runFinale(false)}>
              Продолжить
            </Button>
            <div className="ob-links">
              <button type="button" className="ob-link" onClick={() => setStep(1)}>
                Назад
              </button>
            </div>
          </div>

          {/* Финал */}
          {finale !== null && (
            <div className={phase === "on" && !closing ? "ob-finale on" : "ob-finale"}>
              <div className="ob-fin-mid">
                <div className="ob-fin-spot" ref={spotRef} />
                <h1 className="ob-fin-title">{finTitle}</h1>
                <p className="ob-fin-sub">{finSub}</p>
              </div>
              <div className="ob-fin-actions">
                {error && (
                  <p className="ob-error" role="alert">
                    {error}
                  </p>
                )}
                <Button
                  view="accent"
                  size={48}
                  block
                  loading={busy}
                  disabled={busy}
                  onClick={startWork}
                >
                  Начать работу
                </Button>
                <div className="ob-links">
                  <button
                    type="button"
                    className="ob-link"
                    disabled={busy}
                    onClick={backFromFinale}
                  >
                    Назад
                  </button>
                </div>
              </div>
            </div>
          )}
    </WelcomeShell>
  );
}

/** Обвязка над контекстом: почта из сессии, сохранение через AuthContext —
 * после успешного PATCH state.user получает onboarded_at и Root уводит
 * с онбординга на продукт. */
export function OnboardingView() {
  const { state, saveProfile } = useAuth();
  return <OnboardingScreen email={state.user?.email ?? ""} onSave={saveProfile} />;
}
