import { render, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { ConversationItem } from "../components/ConversationItem";

const conv = { id: "1", title: "Договор аренды", updated_at: "2026-06-27T10:00:00" };

describe("ConversationItem", () => {
  it("рендерит название без иконки, с кнопкой действий", () => {
    const { container } = render(
      <ConversationItem conv={conv} active onOpen={() => {}} onDelete={() => {}} />,
    );
    // дизайн-закон: ряды истории — только текст, без пиктограмм
    expect(container.querySelector(".conv-ico")).toBeNull();
    expect(screen.getByText("Договор аренды")).toBeInTheDocument();
    expect(screen.getByLabelText("Удалить задачу")).toBeInTheDocument();
  });

  it("удаляет через диалог подтверждения", () => {
    const onDelete = vi.fn();
    render(<ConversationItem conv={conv} active={false} onOpen={() => {}} onDelete={onDelete} />);
    fireEvent.click(screen.getByLabelText("Удалить задачу"));
    // диалог открылся, удаление ещё не произошло
    expect(onDelete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it("отмена в диалоге не удаляет", () => {
    const onDelete = vi.fn();
    render(<ConversationItem conv={conv} active={false} onOpen={() => {}} onDelete={onDelete} />);
    fireEvent.click(screen.getByLabelText("Удалить задачу"));
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("клики по диалогу не всплывают в onOpen карточки", () => {
    const onOpen = vi.fn();
    render(<ConversationItem conv={conv} active={false} onOpen={onOpen} onDelete={() => {}} />);
    fireEvent.click(screen.getByLabelText("Удалить задачу"));
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
    fireEvent.click(screen.getByLabelText("Удалить задачу"));
    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
    expect(onOpen).not.toHaveBeenCalled();
  });
});
