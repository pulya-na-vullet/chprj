// Стейт-машина тура по продукту (T-0132, спека E19 §9, эталон
// tour-final-locked2.html): 4 шага спотлайта → финал с автонабором вопроса.
// Чистая логика без DOM — вся геометрия живёт в tourGeometry, отрисовка в
// components/tour/*.

export type TourStepKey = "composer" | "sources" | "files" | "reviews";
export type TipPlacement = "below" | "right";

export interface TourStep {
  key: TourStepKey;
  title: string;
  text: string;
  /** Куда ставить карточку-подсказку относительно выреза. */
  placement: TipPlacement;
  /** Необязательный якорь-«просвет»: карточка не поднимается выше его низа
   * (пилюля источников живёт внутри композера — карточка встаёт под весь
   * композер, как в принятом прототипе, а не под саму пилюлю). */
  clearanceKey?: TourStepKey;
}

// Тексты приняты клиентом в прототипе — не редактировать без новой приёмки.
export const TOUR_STEPS: readonly TourStep[] = [
  {
    key: "composer",
    title: "Задайте вопрос",
    text: "Опишите ситуацию своими словами — ответ будет со ссылками на статьи законов.",
    placement: "below",
  },
  {
    key: "sources",
    title: "Выберите источники",
    text: "Ограничьте поиск нужными кодексами. По умолчанию ищем по всем.",
    placement: "below",
    clearanceKey: "composer",
  },
  {
    key: "files",
    title: "Ваши документы",
    text: "Загружайте договоры и файлы — они хранятся в библиотеке и всегда под рукой.",
    placement: "right",
  },
  {
    key: "reviews",
    title: "Проверка договора",
    text: "Полная проверка на риски со ссылками на нормы. Отчёты сохраняются здесь.",
    placement: "right",
  },
];

// Фаз в мини-полосе прогресса — пять: четыре шага и финал (спека §9).
export const TOUR_PHASES = TOUR_STEPS.length + 1;

// Первый вопрос финала (стартовый; подбор под роль/задачи — вне скоупа MVP).
export const TOUR_FINALE_QUESTION = "Какие сроки ответа на досудебную претензию?";

export interface TourState {
  status: "idle" | "steps" | "finale" | "done";
  /** Индекс текущего шага в TOUR_STEPS (осмыслен при status="steps"). */
  step: number;
  /** Максимум пройденных шагов — счётчик пилюли, не сбрасывается. */
  maxSeen: number;
  /** Тур закрыт «Пропустить» (для отметки tour_completed — без разницы). */
  skipped: boolean;
}

export const initialTourState: TourState = {
  status: "idle",
  step: 0,
  maxSeen: 0,
  skipped: false,
};

export type TourAction = { type: "START" } | { type: "NEXT" } | { type: "SKIP" };

export function tourReducer(state: TourState, action: TourAction): TourState {
  switch (action.type) {
    case "START":
      // И автозапуск, и перезапуск с пилюли: сначала, максимум сохраняется.
      return { ...state, status: "steps", step: 0, maxSeen: Math.max(state.maxSeen, 1) };
    case "NEXT": {
      if (state.status !== "steps") return state;
      if (state.step >= TOUR_STEPS.length - 1) {
        return { ...state, status: "finale", maxSeen: TOUR_STEPS.length };
      }
      const step = state.step + 1;
      return { ...state, step, maxSeen: Math.max(state.maxSeen, step + 1) };
    }
    case "SKIP":
      if (state.status !== "steps") return state;
      return { ...state, status: "done", skipped: true };
  }
}

/** Метка счётчика пилюли: максимум пройденного из четырёх. */
export function pillLabel(maxSeen: number): string {
  return `${Math.min(maxSeen, TOUR_STEPS.length)}/${TOUR_STEPS.length}`;
}

// Порог автоскрытия пилюли: после трёх заданных вопросов (суммарно по всем
// беседам) помощь больше не предлагаем (спека §9).
export const PILL_HIDE_QUESTIONS = 3;

export function isPillVisible(questionsAsked: number): boolean {
  return questionsAsked < PILL_HIDE_QUESTIONS;
}
