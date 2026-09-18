import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FileCard } from "../components/files/FileCard";
import type { HubDocumentInfo } from "../api/types";

const doc: HubDocumentInfo = {
  id: "d1", owner_id: "u1", filename: "Договор аренды.docx",
  content_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  size: 253_952, status: "ready", parser: "docx", page_count: null, error: null,
  summary: "Аренда квартиры на ул. Лесной, 24", created_at: "2026-08-17T10:00:00Z",
};

describe("FileCard", () => {
  it("показывает имя, суть, статус и размер с датой", () => {
    render(
      <FileCard doc={doc} checked={false} onOpen={vi.fn()} onToggleCheck={vi.fn()} menu={<span />} />,
    );
    expect(screen.getByText("Договор аренды.docx")).toBeInTheDocument();
    expect(screen.getByText("Аренда квартиры на ул. Лесной, 24")).toBeInTheDocument();
    expect(screen.getByText("готов")).toBeInTheDocument();
    expect(screen.getByText(/248,0 КБ · 17 авг/)).toBeInTheDocument();
  });

  it("открывает документ по клику", () => {
    const onOpen = vi.fn();
    render(
      <FileCard doc={doc} checked={false} onOpen={onOpen} onToggleCheck={vi.fn()} menu={<span />} />,
    );
    fireEvent.click(screen.getByText("Договор аренды.docx"));
    expect(onOpen).toHaveBeenCalledOnce();
  });

  // Minor 6 (финальное ревью): доступное имя карточки — filename, а не смесь
  // имени/сути/статуса/размера.
  it("несёт доступное имя — aria-label с именем файла", () => {
    render(
      <FileCard doc={doc} checked={false} onOpen={vi.fn()} onToggleCheck={vi.fn()} menu={<span />} />,
    );
    expect(screen.getByRole("button", { name: "Договор аренды.docx" })).toBeInTheDocument();
  });

  // I1 (финальное ревью): та же механика выбора, что и в строке списка —
  // чекбокс, недоступный для не-ready, гасит всплытие клика (не открывает
  // читалку) и не идёт через onOpen.
  it("чекбокс переключает выбор, не открывая читалку", () => {
    const onOpen = vi.fn();
    const onToggleCheck = vi.fn();
    render(
      <FileCard doc={doc} checked={false} onOpen={onOpen} onToggleCheck={onToggleCheck} menu={<span />} />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /Выбрать/ }));
    expect(onToggleCheck).toHaveBeenCalledOnce();
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("чекбокс недоступен для документа не в статусе ready", () => {
    render(
      <FileCard
        doc={{ ...doc, status: "processing" }}
        checked={false}
        onOpen={vi.fn()}
        onToggleCheck={vi.fn()}
        menu={<span />}
      />,
    );
    const checkbox = screen.getByRole("checkbox", { name: /Выбрать/ });
    expect(checkbox).toHaveAttribute("aria-disabled", "true");
    expect(checkbox).toHaveAttribute("tabIndex", "-1");
  });

  it("отражает выбранное состояние в aria-checked и классе карточки", () => {
    const { container } = render(
      <FileCard doc={doc} checked onOpen={vi.fn()} onToggleCheck={vi.fn()} menu={<span />} />,
    );
    expect(screen.getByRole("checkbox", { name: /Выбрать/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(container.querySelector(".file-card-on")).not.toBeNull();
  });
});
