import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FilesView } from "../components/files/FilesView";
import * as api from "../api/client";
import type { HubDocumentInfo } from "../api/types";

const askAboutDocuments = vi.fn();
const clearFileReader = vi.fn();
const openReviewFor = vi.fn();

vi.mock("../state/ChatContext", () => ({
  useChat: () => ({
    askAboutDocuments,
    clearFileReader,
    openReviewFor,
    state: { filesReaderDocId: null },
  }),
}));

function doc(over: Partial<HubDocumentInfo> = {}): HubDocumentInfo {
  return {
    id: "d1",
    owner_id: "default",
    filename: "Договор.pdf",
    content_type: "application/pdf",
    size: 2048,
    status: "ready",
    parser: "pdf",
    page_count: null,
    error: null,
    summary: null,
    created_at: "2026-07-08T00:00:00Z",
    ...over,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  askAboutDocuments.mockClear();
  clearFileReader.mockClear();
  openReviewFor.mockClear();
});

describe("FilesView", () => {
  it("lists documents in the table without opening the reader", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc()]);
    const { container } = render(<FilesView />);
    expect(await screen.findByText("Договор.pdf")).toBeInTheDocument();
    expect(container.querySelector(".files-panel")).toBeNull();
  });

  it("opens the reader panel when a row is clicked", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc()]);
    const { container } = render(<FilesView />);
    fireEvent.click(await screen.findByText("Договор.pdf"));
    await waitFor(() => expect(container.querySelector("iframe.files-pdf")).not.toBeNull());
  });

  it("closes the reader panel when the open row is clicked again", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc()]);
    const { container } = render(<FilesView />);
    const row = await screen.findByText("Договор.pdf");
    fireEvent.click(row);
    await waitFor(() => expect(container.querySelector(".files-panel-open")).not.toBeNull());
    fireEvent.click(row);
    await waitFor(() => expect(container.querySelector(".files-panel")).toBeNull());
  });

  it("shows the server summary in the summary column when present", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([
      doc({ summary: "Договор поставки: предмет и порядок расчётов." }),
    ]);
    render(<FilesView />);
    expect(
      await screen.findByText("Договор поставки: предмет и порядок расчётов."),
    ).toBeInTheDocument();
  });

  it("shows a dash in the summary column for a ready document without a summary", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc({ summary: null })]);
    render(<FilesView />);
    await screen.findByText("Договор.pdf");
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("switches the strip from search to ask mode when a document is checked", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc()]);
    render(<FilesView />);
    await screen.findByText("Договор.pdf");
    expect(screen.getByLabelText("Поиск по документам")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: /Выбрать/ }));
    expect(screen.getByLabelText("Вопрос по выбранным документам")).toBeInTheDocument();
  });

  it("does not allow checking a failed document", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([
      doc({ status: "failed", error: "boom", parser: "docx", filename: "Пакет.docx" }),
    ]);
    render(<FilesView />);
    await screen.findByText("Пакет.docx");
    fireEvent.click(screen.getByRole("checkbox", { name: /Выбрать/ }));
    expect(screen.getByLabelText("Поиск по документам")).toBeInTheDocument();
  });

  it("shows the empty state when there are no documents", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([]);
    render(<FilesView />);
    expect(await screen.findByText(/Перетащите файл/i)).toBeInTheDocument();
  });

  it("shows an error state and lets the user retry", async () => {
    const spy = vi.spyOn(api, "listDocuments").mockRejectedValue(new Error("boom"));
    render(<FilesView />);
    await waitFor(() => expect(screen.getByText(/Не удалось загрузить/i)).toBeInTheDocument());
    expect(spy).toHaveBeenCalled();
  });

  it("показывает статус пилюлей, размер и дату отдельными колонками", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([
      doc({ size: 1_258_291, created_at: "2026-08-17T10:00:00Z" }),
    ]);
    const { container } = render(<FilesView />);
    expect(await screen.findByText("готов")).toBeInTheDocument();
    expect(container.querySelector(".st-pill")).not.toBeNull();
    expect(screen.getByText("1,2 МБ")).toBeInTheDocument();
    expect(screen.getByText(/17 авг/)).toBeInTheDocument();
  });

  it("клик по меню строки не открывает читалку", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc()]);
    const { container } = render(<FilesView />);
    await screen.findByText("Договор.pdf");
    fireEvent.click(screen.getByLabelText("Действия с документом"));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(container.querySelector(".files-panel")).toBeNull();
  });

  it("переключает вид и запоминает выбор", async () => {
    localStorage.clear();
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc()]);
    const { container, unmount } = render(<FilesView />);
    await screen.findByText("Договор.pdf");
    expect(container.querySelector(".files-table")).not.toBeNull();

    fireEvent.click(screen.getByLabelText("Плитка"));
    expect(container.querySelector(".files-grid")).not.toBeNull();
    unmount();

    const second = render(<FilesView />);
    await second.findByText("Договор.pdf");
    expect(second.container.querySelector(".files-grid")).not.toBeNull();
  });

  it("I1: в плитке чекбокс на карточке снимает выбор, поставленный «Спросить в чате»", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc()]);
    const { container } = render(<FilesView />);
    await screen.findByText("Договор.pdf");
    fireEvent.click(screen.getByLabelText("Плитка"));

    fireEvent.click(screen.getByLabelText("Действия с документом"));
    fireEvent.click(screen.getByText("Спросить в чате"));
    expect(screen.getByLabelText("Вопрос по выбранным документам")).toBeInTheDocument();
    expect(container.querySelector(".file-card-on")).not.toBeNull();

    fireEvent.click(screen.getByRole("checkbox", { name: /Выбрать/ }));
    expect(screen.getByLabelText("Поиск по документам")).toBeInTheDocument();
    expect(container.querySelector(".file-card-on")).toBeNull();
  });

  it("I1: чекбокс карточки недоступен для документа не в статусе ready", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc({ status: "processing" })]);
    render(<FilesView />);
    await screen.findByText("Договор.pdf");
    fireEvent.click(screen.getByLabelText("Плитка"));
    expect(screen.getByRole("checkbox", { name: /Выбрать/ })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("I2: в плитке клик по меню не закрывает уже открытую читалку", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc()]);
    const { container } = render(<FilesView />);
    await screen.findByText("Договор.pdf");
    fireEvent.click(screen.getByLabelText("Плитка"));

    const card = screen.getByText("Договор.pdf").closest(".file-card") as HTMLElement;
    fireEvent.click(card);
    await waitFor(() => expect(container.querySelector(".files-panel-open")).not.toBeNull());

    // Сторож внешнего клика слушает mousedown на document — именно он и был
    // источником бага I2 (карточка не входила в whitelist `.files-row`).
    fireEvent.mouseDown(screen.getByLabelText("Действия с документом"));
    fireEvent.click(screen.getByLabelText("Действия с документом"));
    expect(container.querySelector(".files-panel-open")).not.toBeNull();
    expect(screen.getByRole("menu")).toBeInTheDocument();

    // Повторный клик по уже открытой карточке по-прежнему закрывает читалку.
    fireEvent.click(card);
    await waitFor(() => expect(container.querySelector(".files-panel")).toBeNull());
  });

  it("I3: в плитке пустой результат поиска показывает «Ничего не найдено»", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc()]);
    render(<FilesView />);
    await screen.findByText("Договор.pdf");
    fireEvent.click(screen.getByLabelText("Плитка"));
    fireEvent.change(screen.getByLabelText("Поиск по документам"), {
      target: { value: "нет такого документа" },
    });
    expect(await screen.findByText("Ничего не найдено")).toBeInTheDocument();
  });

  it("I5: «Проверить на риски» в меню зовёт openReviewFor с id документа", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc()]);
    render(<FilesView />);
    await screen.findByText("Договор.pdf");
    fireEvent.click(screen.getByLabelText("Действия с документом"));
    fireEvent.click(screen.getByText("Проверить на риски"));
    expect(openReviewFor).toHaveBeenCalledWith("d1");
  });

  it("Minor 9: после «Спросить в чате» фокус уходит в поле вопроса", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc()]);
    render(<FilesView />);
    await screen.findByText("Договор.pdf");
    fireEvent.click(screen.getByLabelText("Действия с документом"));
    fireEvent.click(screen.getByText("Спросить в чате"));
    await waitFor(() =>
      expect(screen.getByLabelText("Вопрос по выбранным документам")).toHaveFocus(),
    );
  });

  it("Minor 12: в плитке во время загрузки показывает скелет карточки", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc()]);
    let resolveUpload: (v: HubDocumentInfo) => void = () => {};
    vi.spyOn(api, "uploadLibraryDocument").mockReturnValue(
      new Promise<HubDocumentInfo>((resolve) => {
        resolveUpload = resolve;
      }),
    );
    const { container } = render(<FilesView />);
    await screen.findByText("Договор.pdf");
    fireEvent.click(screen.getByLabelText("Плитка"));

    const file = new File(["содержимое"], "новый.pdf", { type: "application/pdf" });
    const input = container.querySelector(".files-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(container.querySelector(".file-card-skel")).not.toBeNull());
    resolveUpload(doc({ id: "d2", filename: "новый.pdf" }));
    await waitFor(() => expect(container.querySelector(".file-card-skel")).toBeNull());
  });
});
