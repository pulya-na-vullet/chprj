import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import { AuthApiError } from "../api/auth";
import { AuthView } from "../components/auth/AuthView";

const login = vi.fn();
const register = vi.fn();

vi.mock("../state/AuthContext", () => ({
  useAuth: () => ({
    state: { status: "unauthenticated", user: null, sessionExpired: mockSessionExpired },
    login,
    register,
    logout: vi.fn(),
  }),
}));

let mockSessionExpired = false;

beforeEach(() => {
  mockSessionExpired = false;
  login.mockReset();
  register.mockReset();
});

describe("AuthView — login", () => {
  it("renders the login form by default, without a forgot-password link", () => {
    render(<AuthView />);
    expect(screen.getByRole("heading", { name: "Вход" })).toBeInTheDocument();
    expect(screen.queryByText("Забыли пароль?")).not.toBeInTheDocument();
  });

  it("shows the session-expired note when AuthContext flags it", () => {
    mockSessionExpired = true;
    render(<AuthView />);
    expect(screen.getByText("Сессия истекла — войдите снова.")).toBeInTheDocument();
  });

  it("maps invalid_credentials to a Russian error", async () => {
    login.mockRejectedValue(new AuthApiError(401, "invalid_credentials"));
    render(<AuthView />);
    fireEvent.change(screen.getByLabelText("Почта"), { target: { value: "a@b.ru" } });
    fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "password1" } });
    fireEvent.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByText("Неверная почта или пароль")).toBeInTheDocument();
  });

  it("maps rate_limited to a Russian error", async () => {
    login.mockRejectedValue(new AuthApiError(429, "rate_limited"));
    render(<AuthView />);
    fireEvent.change(screen.getByLabelText("Почта"), { target: { value: "a@b.ru" } });
    fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "password1" } });
    fireEvent.click(screen.getByRole("button", { name: "Войти" }));
    expect(
      await screen.findByText("Слишком много попыток. Подождите несколько минут."),
    ).toBeInTheDocument();
  });
});

describe("AuthView — register", () => {
  it("validates the password client-side, then registers into a live session", async () => {
    register.mockResolvedValue(undefined);
    render(<AuthView />);
    fireEvent.click(screen.getByRole("button", { name: "Регистрация" }));
    expect(screen.getByRole("heading", { name: "Регистрация" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Почта"), { target: { value: "new@b.ru" } });
    fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: "Зарегистрироваться" }));
    expect(await screen.findByText(/не короче 8 символов/)).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "longenough1" } });
    fireEvent.click(screen.getByRole("button", { name: "Зарегистрироваться" }));
    await waitFor(() => expect(register).toHaveBeenCalledWith("new@b.ru", "longenough1"));
    // No "письмо отправлено" screen: AuthContext flips to authenticated and
    // the shell takes over — AuthView itself has nothing more to show.
    expect(screen.queryByText("Письмо отправлено")).not.toBeInTheDocument();
  });

  it("maps email_taken to a Russian error", async () => {
    register.mockRejectedValue(new AuthApiError(409, "email_taken"));
    render(<AuthView />);
    fireEvent.click(screen.getByRole("button", { name: "Регистрация" }));
    fireEvent.change(screen.getByLabelText("Почта"), { target: { value: "dup@b.ru" } });
    fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "longenough1" } });
    fireEvent.click(screen.getByRole("button", { name: "Зарегистрироваться" }));
    expect(await screen.findByText(/уже зарегистрирован/i)).toBeInTheDocument();
  });

  it("returns to the login screen", () => {
    render(<AuthView />);
    fireEvent.click(screen.getByRole("button", { name: "Регистрация" }));
    fireEvent.click(screen.getByRole("button", { name: "Уже есть аккаунт? Войти" }));
    expect(screen.getByRole("heading", { name: "Вход" })).toBeInTheDocument();
  });
});

describe("AuthView — композиция онбординга (T-0129)", () => {
  it("рендерит общую оболочку: бренд сверху, превью продукта, футер", () => {
    render(<AuthView />);
    expect(screen.getByText("Нейроюрист")).toBeInTheDocument();
    expect(screen.getByText("© 2026 Нейроюрист")).toBeInTheDocument();
    expect(screen.getByText("Конфиденциальность")).toBeInTheDocument();
    expect(screen.getByText("Поддержка")).toBeInTheDocument();
  });
});
