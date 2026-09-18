import { render, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { Plus } from "lucide-react";
import { Button, IconButton, Input, PasswordInput } from "../ui";

describe("ui/Button", () => {
  it("рендерит кнопку с текстом и кликается", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Новая задача</Button>);
    const btn = screen.getByRole("button", { name: "Новая задача" });
    fireEvent.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("прокидывает className", () => {
    render(<Button className="new-chat">X</Button>);
    expect(screen.getByRole("button")).toHaveClass("new-chat");
  });
});

describe("ui/IconButton", () => {
  it("рендерит кнопку с aria-label и кликается", () => {
    const onClick = vi.fn();
    render(<IconButton icon={<Plus size={17} />} aria-label="Добавить" onClick={onClick} />);
    const btn = screen.getByRole("button", { name: "Добавить" });
    fireEvent.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("блокируется через disabled", () => {
    render(<IconButton icon={<Plus />} aria-label="X" disabled />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});

describe("ui/Input", () => {
  it("рендерит лейбл и отдаёт значение строкой в onChange", () => {
    const onChange = vi.fn();
    render(<Input label="Почта" value="" onChange={onChange} />);
    const field = screen.getByLabelText("Почта");
    fireEvent.change(field, { target: { value: "a@b.ru" } });
    expect(onChange).toHaveBeenCalledWith("a@b.ru");
  });

  it("показывает ошибку", () => {
    render(<Input label="Почта" value="" onChange={() => {}} error="Неверный адрес" />);
    expect(screen.getByText("Неверный адрес")).toBeInTheDocument();
  });
});

describe("ui/PasswordInput", () => {
  it("рендерит поле пароля и отдаёт значение строкой", () => {
    const onChange = vi.fn();
    render(<PasswordInput label="Пароль" value="" onChange={onChange} />);
    const field = screen.getByLabelText("Пароль");
    fireEvent.change(field, { target: { value: "secret123" } });
    expect(onChange).toHaveBeenCalledWith("secret123");
  });

  it("имеет кнопку показа пароля", () => {
    render(<PasswordInput label="Пароль" value="secret123" onChange={() => {}} />);
    // core password-input ships a visibility toggle as an addon button.
    expect(screen.getAllByRole("button").length).toBeGreaterThan(0);
  });
});
