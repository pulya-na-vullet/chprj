import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import * as api from "../api/client";
import type { HubDocumentInfo } from "../api/types";
import { FilePickerModal } from "../components/templates/FilePickerModal";

function doc(over: Partial<HubDocumentInfo> = {}): HubDocumentInfo {
  return {
    id: "d1",
    owner_id: "u",
    filename: "Договор аренды 2024.pdf",
    content_type: "application/pdf",
    size: 1000,
    status: "ready",
    parser: "pdf",
    page_count: null,
    error: null,
    summary: "Аренда 2-к квартиры на Ленина 12",
    created_at: "2026-05-12T10:00:00Z",
    ...over,
  };
}

afterEach(() => vi.restoreAllMocks());

function setup(docs: HubDocumentInfo[]) {
  vi.spyOn(api, "listDocuments").mockResolvedValue(docs);
  const onPick = vi.fn();
  const onClose = vi.fn();
  render(<FilePickerModal onClose={onClose} onPick={onPick} />);
  return { onPick, onClose };
}

describe("FilePickerModal", () => {
  it("диалог с aria, строки с «Сутью»; не-ready документы скрыты", async () => {
    setup([
      doc(),
      doc({ id: "d2", filename: "Скан.pdf", status: "processing", summary: null }),
    ]);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Из моих файлов")).toBeInTheDocument();
    expect(screen.getByText("Аренда 2-к квартиры на Ленина 12")).toBeInTheDocument();
    expect(screen.queryByText("Скан.pdf")).not.toBeInTheDocument();
  });

  it("поиск фильтрует по имени и «Сути»", async () => {
    setup([doc(), doc({ id: "d2", filename: "Реквизиты ИП.docx", parser: "docx", summary: "ИНН и ОГРНИП" })]);
    await screen.findByText("Договор аренды 2024.pdf");
    fireEvent.change(screen.getByPlaceholderText("Поиск по файлам"), { target: { value: "огрнип" } });
    expect(screen.queryByText("Договор аренды 2024.pdf")).not.toBeInTheDocument();
    expect(screen.getByText("Реквизиты ИП.docx")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Поиск по файлам"), { target: { value: "ничего" } });
    expect(screen.getByText("Ничего не нашлось")).toBeInTheDocument();
  });

  it("«Приложить» активна только после выбора и отдаёт документ", async () => {
    const { onPick } = setup([doc()]);
    await screen.findByText("Договор аренды 2024.pdf");
    const confirm = screen.getByRole("button", { name: "Приложить" });
    expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: /Договор аренды 2024\.pdf/ }));
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: "d1" }));
  });

  it("Esc закрывает модалку (a11y core-components)", async () => {
    const { onClose } = setup([doc()]);
    const dialog = await screen.findByRole("dialog");
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("фокус живёт внутри диалога (trap на открытии)", async () => {
    setup([doc()]);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => {
      expect(dialog.contains(document.activeElement)).toBe(true);
    });
  });
});
