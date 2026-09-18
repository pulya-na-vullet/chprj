import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { Composer } from "../components/Composer";

/**
 * T-0012: во время стрима кнопка «Отправить» в Composer заменяется на
 * кнопку-стоп, зовущую useChat().stop(); disabled пока state.stopping.
 */

const stopMock = vi.fn();
const prefillComposerMock = vi.fn();
const uploadFileMock = vi.fn();
const setAttachIntentMock = vi.fn();

function mockState(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    conversations: [],
    currentId: null,
    messages: [],
    streaming: false,
    stopping: false,
    working: null,
    draftAnswer: "",
    draftCitations: [],
    pendingUser: null,
    acts: [],
    actsFull: [],
    documents: [],
    reviewProgress: null,
    selectedSources: [],
    composerPrefill: null,
    banner: null,
    sidebarCollapsed: false,
    actsStatus: "ready",
    actsError: null,
    turnId: 1,
    ...overrides,
  };
}

let currentState = mockState();
const openFilePickerMock = vi.fn();

vi.mock("../state/ChatContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state/ChatContext")>();
  return {
    ...actual,
    useChat: vi.fn(() => ({
      state: currentState,
      send: vi.fn(),
      stop: stopMock,
      uploadFile: uploadFileMock,
      setBanner: vi.fn(),
      setAttachIntent: setAttachIntentMock,
      clearAttachIntent: vi.fn(),
      openFilePicker: openFilePickerMock,
      toggleSource: vi.fn(),
      retryActs: vi.fn(),
      prefillComposer: prefillComposerMock,
    })),
  };
});

describe("Composer stop button", () => {
  it("во время стрима кнопка — «Остановить генерацию» и зовёт stop()", () => {
    currentState = mockState({ streaming: true, stopping: false });
    render(<Composer />);
    const btn = screen.getByRole("button", { name: "Остановить генерацию" });
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    expect(stopMock).toHaveBeenCalled();
  });

  it("stopping=true — кнопка стопа задизейблена", () => {
    currentState = mockState({ streaming: true, stopping: true });
    render(<Composer />);
    const btn = screen.getByRole("button", { name: "Остановить генерацию" });
    expect(btn).toBeDisabled();
  });

  it("вне стрима — обычная кнопка «Отправить»", () => {
    currentState = mockState({ streaming: false, stopping: false });
    render(<Composer />);
    expect(screen.getByRole("button", { name: "Отправить" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Остановить генерацию" })).not.toBeInTheDocument();
  });
});

/**
 * T-0010/Задача 5: «Обсудить в чате» / «Обсудить риски в чате» queue text via
 * ChatContext.prefillComposer(text) → state.composerPrefill. Composer picks
 * it up in a useEffect: inserts it as the textarea value and clears it back
 * (prefillComposer("")) so the effect doesn't refire.
 */
describe("Composer prefill", () => {
  beforeEach(() => {
    prefillComposerMock.mockClear();
  });

  it("composerPrefill set — inserted into the textarea and cleared", () => {
    currentState = mockState({ composerPrefill: "Про риск «Неустойка»: " });
    render(<Composer />);
    expect(screen.getByLabelText("Ваш запрос")).toHaveValue("Про риск «Неустойка»: ");
    expect(prefillComposerMock).toHaveBeenCalledWith("");
  });

  it("composerPrefill null — textarea stays empty, prefillComposer not called", () => {
    currentState = mockState({ composerPrefill: null });
    render(<Composer />);
    expect(screen.getByLabelText("Ваш запрос")).toHaveValue("");
    expect(prefillComposerMock).not.toHaveBeenCalled();
  });
});


describe("Composer attach menu (T-0054)", () => {
  beforeEach(() => {
    uploadFileMock.mockReset();
    setAttachIntentMock.mockReset();
    currentState = mockState();
  });

  it("клик по скрепке открывает меню с двумя сценариями", () => {
    render(<Composer />);
    fireEvent.click(screen.getByRole("button", { name: "Прикрепить документ" }));
    expect(screen.getByRole("menuitem", { name: /Проверить на риски/ })).toBeInTheDocument();
    expect(screen.getByText("Отчет со ссылками на нормы права")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Задать вопрос по документу/ })).toBeInTheDocument();
    expect(screen.getByText("Ответы по тексту документа")).toBeInTheDocument();
  });

  it("пункт запоминает намерение: файл-диалог, после загрузки — setAttachIntent", async () => {
    uploadFileMock.mockResolvedValue({ id: "d9", status: "processing" });
    const clickSpy = vi.spyOn(HTMLInputElement.prototype, "click");
    const { container } = render(<Composer />);

    fireEvent.click(screen.getByRole("button", { name: "Прикрепить документ" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Проверить на риски/ }));

    expect(clickSpy).toHaveBeenCalled(); // открыт выбор файла
    expect(screen.queryByRole("menu")).not.toBeInTheDocument(); // меню закрылось

    const input = container.querySelector("input[type=file]") as HTMLInputElement;
    const file = new File(["x"], "dogovor.docx");
    await vi.waitFor(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      expect(uploadFileMock).toHaveBeenCalled();
    });
    await vi.waitFor(() => {
      expect(setAttachIntentMock).toHaveBeenCalledWith({ docId: "d9", intent: "review" });
    });
    clickSpy.mockRestore();
  });

  it("Escape закрывает меню, намерение не выставляется без выбора файла", () => {
    render(<Composer />);
    fireEvent.click(screen.getByRole("button", { name: "Прикрепить документ" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(setAttachIntentMock).not.toHaveBeenCalled();
  });
});

/** E20 (T-0137): скрепка получила третий пункт «Из моих файлов» — открывает
 * пикер библиотеки; существующие пункты загрузки остаются на месте. */
describe("Composer attach menu (E20)", () => {
  it("пункт «Из моих файлов» открывает пикер, старые пункты не пропали", () => {
    openFilePickerMock.mockClear();
    currentState = mockState({ streaming: false, stopping: false });
    render(<Composer />);
    fireEvent.click(screen.getByRole("button", { name: "Прикрепить документ" }));
    expect(screen.getByRole("menuitem", { name: /Проверить на риски/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Задать вопрос по документу/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("menuitem", { name: /Из моих файлов/ }));
    expect(openFilePickerMock).toHaveBeenCalledWith("attach");
  });
});
