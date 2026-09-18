import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { NewReviewDialog } from "../components/reviews/NewReviewDialog";
import * as api from "../api/client";
import type { HubDocumentInfo, PlaybookInfo } from "../api/types";

function doc(over: Partial<HubDocumentInfo> = {}): HubDocumentInfo {
  return {
    id: "d1",
    owner_id: "u",
    filename: "договор.pdf",
    content_type: "application/pdf",
    size: 1000,
    status: "ready",
    parser: "pdf",
    page_count: null,
    error: null,
    summary: null,
    created_at: "2026-07-18T10:00:00Z",
    ...over,
  };
}

const PLAYBOOKS: PlaybookInfo[] = [
  { id: "supply_ru", name: "Договор поставки", rules_count: 12, roles: ["Покупатель", "Поставщик"] },
  { id: "lease_ru", name: "Аренда", rules_count: 10, roles: [] },
];

afterEach(() => vi.restoreAllMocks());

function setup(docs: HubDocumentInfo[] = [doc()]) {
  vi.spyOn(api, "listDocuments").mockResolvedValue(docs);
  vi.spyOn(api, "listPlaybooks").mockResolvedValue(PLAYBOOKS);
  const onStart = vi.fn();
  const onClose = vi.fn();
  render(<NewReviewDialog onStart={onStart} onClose={onClose} />);
  return { onStart, onClose };
}

describe("NewReviewDialog", () => {
  it("списки: документы библиотеки и плейбуки; не-ready документ недоступен", async () => {
    setup([doc(), doc({ id: "d2", filename: "скан.pdf", status: "processing" })]);
    expect(await screen.findByRole("radio", { name: /договор\.pdf/ })).toBeEnabled();
    expect(screen.getByRole("radio", { name: /скан\.pdf/ })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /Договор поставки/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Аренда/ })).toBeInTheDocument();
  });

  it("роль: чипы выбранного плейбука + свой вариант; кнопка активна только с полным выбором", async () => {
    setup();
    const start = await screen.findByRole("button", { name: "Запустить" });
    expect(start).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: /договор\.pdf/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Договор поставки/ }));
    expect(start).toBeDisabled(); // роли ещё нет
    fireEvent.click(screen.getByRole("button", { name: "Покупатель" }));
    expect(start).toBeEnabled();
  });

  it("свободная роль из поля перекрывает чип", async () => {
    const { onStart } = setup();
    fireEvent.click(await screen.findByRole("radio", { name: /договор\.pdf/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Договор поставки/ }));
    fireEvent.change(screen.getByPlaceholderText(/апишите/), {
      target: { value: "Грузополучатель" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Запустить" }));
    await waitFor(() =>
      expect(onStart).toHaveBeenCalledWith({
        documentId: "d1",
        filename: "договор.pdf",
        playbookId: "supply_ru",
        playbookName: "Договор поставки",
        role: "Грузополучатель",
      }),
    );
  });

  it("загрузка файла добавляет документ в список и выбирает его", async () => {
    setup([]);
    const uploaded = doc({ id: "dn", filename: "новый.docx", parser: "docx", status: "ready" });
    vi.spyOn(api, "uploadLibraryDocument").mockResolvedValue(uploaded);
    const input = (await screen.findByLabelText("Загрузить документ")) as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(["x"], "новый.docx")] },
    });
    const radio = await screen.findByRole("radio", { name: /новый\.docx/ });
    expect(radio).toBeChecked();
  });

  it("плейбук без ролей (T-0070): поле роли не отображается, кнопка активна без роли", async () => {
    const { onStart } = setup();
    fireEvent.click(await screen.findByRole("radio", { name: /договор\.pdf/ }));
    const start = screen.getByRole("button", { name: "Запустить" });
    expect(start).toBeDisabled(); // плейбук ещё не выбран

    fireEvent.click(screen.getByRole("radio", { name: /Аренда/ }));

    expect(screen.queryByText("Ваша роль по договору")).toBeNull();
    expect(screen.queryByRole("button", { name: "Покупатель" })).toBeNull();
    expect(screen.queryByLabelText("Своя роль")).toBeNull();
    expect(start).toBeEnabled();

    fireEvent.click(start);
    await waitFor(() => expect(onStart).toHaveBeenCalled());
    expect(onStart.mock.calls[0][0]).toEqual({
      documentId: "d1",
      filename: "договор.pdf",
      playbookId: "lease_ru",
      playbookName: "Аренда",
      role: "",
    });
  });
});
