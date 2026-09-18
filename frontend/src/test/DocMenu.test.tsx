import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DocMenu } from "../components/files/DocMenu";
import type { HubDocumentInfo } from "../api/types";

function doc(over: Partial<HubDocumentInfo> = {}): HubDocumentInfo {
  return {
    id: "d1", owner_id: "u1", filename: "Договор.pdf",
    content_type: "application/pdf", size: 2048, status: "ready", parser: "pdf",
    page_count: null, error: null, summary: null,
    created_at: "2026-08-17T00:00:00Z", ...over,
  };
}

function setup(over: Partial<HubDocumentInfo> = {}) {
  const handlers = { onOpen: vi.fn(), onAsk: vi.fn(), onReview: vi.fn(), onDelete: vi.fn() };
  render(<DocMenu doc={doc(over)} downloadUrl="/documents/d1/download" {...handlers} />);
  return handlers;
}

describe("DocMenu", () => {
  it("открывает меню и вызывает действие, не всплывая наружу", () => {
    const outer = vi.fn();
    const handlers = { onOpen: vi.fn(), onAsk: vi.fn(), onReview: vi.fn(), onDelete: vi.fn() };
    render(
      <div onClick={outer}>
        <DocMenu doc={doc()} downloadUrl="/d" {...handlers} />
      </div>,
    );
    fireEvent.click(screen.getByLabelText("Действия с документом"));
    fireEvent.click(screen.getByText("Открыть"));
    expect(handlers.onOpen).toHaveBeenCalledOnce();
    expect(outer).not.toHaveBeenCalled();
  });

  it("закрывается по Escape", () => {
    setup();
    fireEvent.click(screen.getByLabelText("Действия с документом"));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("не даёт спросить и проверить документ без текста (processing)", () => {
    const handlers = setup({ status: "processing" });
    fireEvent.click(screen.getByLabelText("Действия с документом"));
    const ask = screen.getByText("Спросить в чате");
    expect(ask).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(ask);
    expect(handlers.onAsk).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Проверить на риски"));
    expect(handlers.onReview).not.toHaveBeenCalled();
  });

  // Minor 18 (финальное ревью): тот же сценарий отдельно для failed —
  // раньше был покрыт только processing.
  it("не даёт спросить и проверить документ без текста (failed)", () => {
    const handlers = setup({ status: "failed" });
    fireEvent.click(screen.getByLabelText("Действия с документом"));
    const ask = screen.getByText("Спросить в чате");
    expect(ask).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(ask);
    expect(handlers.onAsk).not.toHaveBeenCalled();
    const review = screen.getByText("Проверить на риски");
    expect(review).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(review);
    expect(handlers.onReview).not.toHaveBeenCalled();
  });

  // Minor 3 (финальное ревью): разделитель — role=separator, а не голый div
  // без роли внутри role=menu.
  it("разделитель пунктов меню несёт role=separator", () => {
    setup();
    fireEvent.click(screen.getByLabelText("Действия с документом"));
    const sep = document.querySelector(".files-menu-sep");
    expect(sep).toHaveAttribute("role", "separator");
  });

  // Minor 10 (финальное ревью): «Скачать» должен скачивать (download),
  // а не открывать превью в новой вкладке.
  it("«Скачать» — ссылка со скачиванием, а не превью", () => {
    setup();
    fireEvent.click(screen.getByLabelText("Действия с документом"));
    const link = screen.getByText("Скачать");
    expect(link).toHaveAttribute("download", "Договор.pdf");
  });

  // Minor 7 (финальное ревью): Esc при открытом меню закрывает только его —
  // не должен доходить до bubble-обработчиков выше по дереву (например,
  // закрытия читалки в FilesView, тоже висящего на document).
  it("Esc с открытым меню не даёт событию дойти до внешнего слушателя", () => {
    const outer = vi.fn();
    document.addEventListener("keydown", outer);
    try {
      setup();
      const trigger = screen.getByLabelText("Действия с документом");
      fireEvent.click(trigger);
      expect(screen.getByRole("menu")).toBeInTheDocument();
      fireEvent.keyDown(trigger, { key: "Escape" });
      expect(screen.queryByRole("menu")).toBeNull();
      expect(outer).not.toHaveBeenCalled();
    } finally {
      document.removeEventListener("keydown", outer);
    }
  });

  // I0 (финальное ревью, живая проверка): .doc-menu уже занят абсолютно
  // спозиционированным меню скрепки композера (composer.css) — та же обёртка
  // на строке/карточке улетала за пределы окна. Класс обёртки должен быть
  // уникальным.
  it("класс обёртки не пересекается с .doc-menu композера", () => {
    const { container } = render(
      <DocMenu
        doc={doc()}
        downloadUrl="/d"
        onOpen={vi.fn()}
        onAsk={vi.fn()}
        onReview={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    const wrap = container.querySelector(".files-menu-wrap");
    expect(wrap).not.toBeNull();
    expect(wrap).toHaveClass("files-row-menu");
    expect(wrap).not.toHaveClass("doc-menu");
  });
});
