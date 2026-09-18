// Экран профиль-онбординга (T-0127, спека E19 §3): переходы шагов, ветки
// personal/business, пропуск, сборка PATCH-запроса. Тестируем чистый
// OnboardingScreen (email + onSave пропсами), без AuthProvider.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { OnboardingScreen, buildProfileRequest } from "../components/onboarding/OnboardingView";

function renderScreen(onSave = vi.fn(() => Promise.resolve())) {
  render(<OnboardingScreen email="user@example.com" onSave={onSave} />);
  return onSave;
}

function setReducedMotion(reduce: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: reduce,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

describe("OnboardingScreen: шаги (T-0127)", () => {
  it("шаг 1: знакомство, почта из сессии недоступна для правки", () => {
    renderScreen();
    expect(screen.getByRole("heading", { name: "Давайте познакомимся" })).toBeInTheDocument();
    const email = screen.getByDisplayValue("user@example.com");
    expect(email).toBeDisabled();
  });

  it("«Продолжить» ведёт на шаг 2, «Назад» возвращает с сохранённым именем", () => {
    renderScreen();
    fireEvent.change(screen.getByLabelText("Имя"), { target: { value: "Денис" } });
    fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(
      screen.getByRole("heading", { name: "Пара слов о ваших задачах" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Назад" }));
    expect(screen.getByRole("heading", { name: "Давайте познакомимся" })).toBeInTheDocument();
    expect(screen.getByLabelText("Имя")).toHaveValue("Денис");
  });

  it("инициалы в аватаре собираются из имени и фамилии", () => {
    renderScreen();
    fireEvent.change(screen.getByLabelText("Имя"), { target: { value: "денис" } });
    fireEvent.change(screen.getByLabelText("Фамилия"), { target: { value: "анастасьев" } });
    expect(screen.getByTestId("ob-avatar")).toHaveTextContent("ДА");
  });

  it("6 свотчей; выбор пресета переключает активный", () => {
    renderScreen();
    const swatches = screen.getAllByRole("radio", { name: /Пресет \d/ });
    expect(swatches).toHaveLength(6);
    expect(swatches[0]).toBeChecked();
    fireEvent.click(swatches[3]);
    expect(swatches[3]).toBeChecked();
    expect(swatches[0]).not.toBeChecked();
  });
});

describe("OnboardingScreen: шаг 2 — сегмент, роль, задачи", () => {
  function toStep2() {
    fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));
  }

  it("дефолт «Для себя»: роли нет, задачи в формулировках для физлица", () => {
    renderScreen();
    toStep2();
    expect(screen.queryByText("Ваша роль")).not.toBeInTheDocument();
    expect(screen.getByText("Вопросы по законам")).toBeInTheDocument();
    expect(screen.getByText("Права, обязанности и сроки — простым языком")).toBeInTheDocument();
  });

  it("«Для бизнеса»: появляются 4 чипа роли и бизнес-формулировки задач", () => {
    renderScreen();
    toStep2();
    fireEvent.click(screen.getByRole("button", { name: "Для бизнеса" }));
    expect(screen.getByText("Ваша роль")).toBeInTheDocument();
    for (const role of ["Юрист", "Бухгалтер", "Руководитель", "Другое"]) {
      expect(screen.getByRole("button", { name: role })).toBeInTheDocument();
    }
    expect(screen.getByText("Вопросы по законодательству")).toBeInTheDocument();

    // обратно к «Для себя» — роль скрывается
    fireEvent.click(screen.getByRole("button", { name: "Для себя" }));
    expect(screen.queryByText("Ваша роль")).not.toBeInTheDocument();
  });

  it("задачи — мультивыбор с переключением", () => {
    renderScreen();
    toStep2();
    const row = screen.getByRole("button", { name: /Вопросы по законам/ });
    const row2 = screen.getByRole("button", { name: /Проверка договоров/ });
    fireEvent.click(row);
    fireEvent.click(row2);
    expect(row).toHaveAttribute("aria-pressed", "true");
    expect(row2).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-pressed", "false");
    expect(row2).toHaveAttribute("aria-pressed", "true");
  });
});

describe("OnboardingScreen: финал и сохранение", () => {
  it("ветка пропуска: «Заполнить позже» → финал → PATCH только с onboarded", async () => {
    const onSave = renderScreen();
    fireEvent.click(screen.getByRole("button", { name: "Заполнить позже" }));
    expect(
      screen.getByText("Профиль можно заполнить позже — в любой момент в настройках."),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Готово" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Начать работу" }));
    await vi.waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith({ onboarded: true });
  });

  it("полный путь: поля + бизнес-роль + задачи доезжают в PATCH", async () => {
    const onSave = renderScreen();
    fireEvent.change(screen.getByLabelText("Имя"), { target: { value: "Денис" } });
    fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    fireEvent.click(screen.getByRole("button", { name: "Для бизнеса" }));
    fireEvent.click(screen.getByRole("button", { name: "Юрист" }));
    fireEvent.click(screen.getByRole("button", { name: /Вопросы по законодательству/ }));
    fireEvent.click(screen.getByRole("button", { name: /Работа со своими файлами/ }));
    fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));

    expect(screen.getByRole("heading", { name: "Готово, Денис" })).toBeInTheDocument();
    expect(
      screen.getByText("Профиль сохранён — ответы настроены под ваши задачи."),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Начать работу" }));
    await vi.waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith({
      first_name: "Денис",
      avatar_preset: 0,
      usage_kind: "business",
      role: "lawyer",
      tasks: ["law_questions", "files"],
      onboarded: true,
    });
  });

  it("«Назад» с финала возвращает на шаг 2 без сохранения", async () => {
    vi.useFakeTimers();
    try {
      const onSave = vi.fn(() => Promise.resolve());
      render(<OnboardingScreen email="user@example.com" onSave={onSave} />);
      fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));
      fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));
      expect(screen.getByRole("heading", { name: "Готово" })).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Назад" }));
      act(() => vi.advanceTimersByTime(1000));
      expect(
        screen.getByRole("heading", { name: "Пара слов о ваших задачах" }),
      ).toBeInTheDocument();
      expect(onSave).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("OnboardingScreen: доступность (T-0143)", () => {
  it("сегмент «Для себя / Для бизнеса» сообщает состояние", () => {
    renderScreen();
    fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    const personal = screen.getByRole("button", { name: "Для себя" });
    const business = screen.getByRole("button", { name: "Для бизнеса" });
    expect(personal).toHaveAttribute("aria-pressed", "true");
    expect(business).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(business);
    expect(business).toHaveAttribute("aria-pressed", "true");
    expect(personal).toHaveAttribute("aria-pressed", "false");
  });

  it("prefers-reduced-motion: финал доступен сразу, без двух секунд ожидания", () => {
    setReducedMotion(true);
    vi.useFakeTimers();
    try {
      renderScreen();
      fireEvent.click(screen.getByRole("button", { name: "Заполнить позже" }));
      // .on снимает pointer-events: none — до него «Начать работу» некликабельна
      expect(document.querySelector(".ob-finale")).toHaveClass("on");
    } finally {
      vi.useRealTimers();
      setReducedMotion(false);
    }
  });

  it("без этой настройки финал по-прежнему проявляется анимацией", () => {
    setReducedMotion(false);
    vi.useFakeTimers();
    try {
      renderScreen();
      fireEvent.click(screen.getByRole("button", { name: "Заполнить позже" }));
      expect(document.querySelector(".ob-finale")).not.toHaveClass("on");
      act(() => vi.advanceTimersByTime(2100));
      expect(document.querySelector(".ob-finale")).toHaveClass("on");
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("buildProfileRequest", () => {
  it("пропуск — только onboarded, без avatar_preset", () => {
    expect(
      buildProfileRequest({
        skipped: true,
        firstName: "Денис",
        lastName: "",
        preset: 2,
        usageKind: "business",
        role: "lawyer",
        tasks: ["files"],
      }),
    ).toEqual({ onboarded: true });
  });

  it("пустые имя/фамилия не отправляются; роль вне бизнеса отбрасывается", () => {
    expect(
      buildProfileRequest({
        skipped: false,
        firstName: "  ",
        lastName: "",
        preset: 4,
        usageKind: "personal",
        role: "lawyer",
        tasks: [],
      }),
    ).toEqual({ avatar_preset: 4, usage_kind: "personal", onboarded: true });
  });
});
