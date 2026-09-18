import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import type { DocumentReadyData, Message, ServerEvent, TemplateDraftData } from "../api/types";
import { AssistantMessage } from "../components/AssistantMessage";
import { TemplateDocCard } from "../components/templates/TemplateDocCard";
import { TemplateDraftCard } from "../components/templates/TemplateDraftCard";
import { templateAskAction } from "../components/MessageList";
import { applyServerEvent, chatReducer, initialState } from "../state/chatReducer";

const DRAFT: TemplateDraftData = {
  template: { slug: "arenda-kvartiry", title: "Договор аренды квартиры" },
  fields: [
    { name: "landlord_fio", label: "Арендодатель", value: "Иванов Иван", source: "document" },
    { name: "tenant_fio", label: "Арендатор", value: "Анастасьев Денис", source: "profile" },
    { name: "rent", label: "Плата в месяц", value: "65 000", source: "user" },
  ],
};

const DOC_READY: DocumentReadyData = {
  document_id: "doc-9",
  filename: "Договор аренды.docx",
  fields_filled: 12,
};

describe("TemplateDraftCard", () => {
  it("рендерит шапку, строки поле→значение и пилюли источников", () => {
    render(<TemplateDraftCard data={DRAFT} />);
    expect(screen.getByText("Договор аренды квартиры")).toBeInTheDocument();
    expect(screen.getByText("3 поля")).toBeInTheDocument();
    expect(screen.getByText("Арендодатель")).toBeInTheDocument();
    expect(screen.getByText("Иванов Иван")).toBeInTheDocument();
    expect(screen.getByText("из документа")).toBeInTheDocument();
    expect(screen.getByText("из профиля")).toBeInTheDocument();
    expect(screen.getByText("уточнили")).toBeInTheDocument();
  });
});

describe("TemplateDocCard", () => {
  it("«Скачать» тянет download-прокси хаба, «Открыть» зовёт onOpen", () => {
    const onOpen = vi.fn();
    render(<TemplateDocCard data={DOC_READY} onOpen={onOpen} />);
    const download = screen.getByRole("link", { name: "Скачать" });
    expect(download).toHaveAttribute("href", "/documents/doc-9/download");
    expect(screen.getByText(/12 полей заполнено · сохранён в «Файлы»/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Открыть" }));
    expect(onOpen).toHaveBeenCalledWith("doc-9");
  });
});

describe("reducer: шаблонные SSE-события и живучесть", () => {
  const sse = (ev: ServerEvent) => ev;

  it("template_draft и document_ready складываются в финализированное сообщение", () => {
    let state = chatReducer(initialState, {
      type: "START_TURN",
      user: {
        id: "u-m",
        role: "user",
        content: "Сформировать",
        citations: null,
        stopped: false,
        created_at: "2026-08-13T00:00:00Z",
      },
    });
    state = applyServerEvent(state, sse({ event: "template_draft", data: DRAFT }));
    state = applyServerEvent(state, sse({ event: "document_ready", data: DOC_READY }));
    state = applyServerEvent(state, sse({ event: "delta", data: { text: "Готово" } }));
    expect(state.draftTemplateDraft).toEqual(DRAFT);
    expect(state.draftTemplateDoc).toEqual(DOC_READY);

    const finished = chatReducer(state, { type: "FINISH_TURN", turnId: state.turnId });
    const last = finished.messages[finished.messages.length - 1];
    expect(last.template_draft).toEqual(DRAFT);
    expect(last.template_doc).toEqual(DOC_READY);
    expect(finished.draftTemplateDraft).toBeNull();
    expect(finished.draftTemplateDoc).toBeNull();
  });

  it("OPEN_FILE_READER переключает вид и хранит одноразовый id", () => {
    let state = chatReducer(initialState, { type: "OPEN_FILE_READER", docId: "doc-9" });
    expect(state.view).toBe("files");
    expect(state.filesReaderDocId).toBe("doc-9");
    state = chatReducer(state, { type: "CLEAR_FILE_READER" });
    expect(state.filesReaderDocId).toBeNull();
  });

  it("сообщение из истории (перезагрузка) рендерит панель и карточку", () => {
    // как после GET /conversations/{id}/messages: payload'ы лежат на сообщении
    const message: Message = {
      id: "m1",
      role: "assistant",
      content: "Все поля собраны:",
      citations: null,
      stopped: false,
      created_at: "2026-08-13T00:00:00Z",
      template_draft: DRAFT,
      template_doc: DOC_READY,
    };
    render(
      <AssistantMessage
        content={message.content}
        citations={message.citations}
        actNames={[]}
        templateDraft={message.template_draft}
        templateDoc={message.template_doc}
      />,
    );
    expect(screen.getByText("Договор аренды квартиры")).toBeInTheDocument();
    expect(screen.getByText("Договор аренды.docx")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Скачать" })).toBeInTheDocument();
  });

  it("карточки стоят над текстом сообщения: stage/render случились до текста", () => {
    // Замечание клиента (T-0141): текст стримится после карточки и должен
    // дописываться вниз, а не печататься над уже показанной сводкой.
    const { container } = render(
      <AssistantMessage
        content="Всё верно, сформировать документ?"
        citations={null}
        actNames={[]}
        templateDraft={DRAFT}
        templateDoc={DOC_READY}
      />,
    );
    const card = container.querySelector(".tpld")!;
    const doc = container.querySelector(".tpldoc")!;
    const text = screen.getByText("Всё верно, сформировать документ?");
    expect(card.compareDocumentPosition(text) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(doc.compareDocumentPosition(text) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("templateAskAction: перехват только шаблонных ask'ов", () => {
  const ask = (template: boolean) =>
    ({ kind: "ask_user", options: [], template }) as import("../api/types").MessageAsk;

  it("нешаблонный ask с «файл»-вариантом остаётся обычным ответом", () => {
    expect(templateAskAction(ask(false), "У меня нет файла")).toBeNull();
    expect(templateAskAction(ask(false), "Выбрать из «Файлов»")).toBeNull();
    expect(templateAskAction(ask(false), "Загрузить документ")).toBeNull();
  });

  it("шаблонный ask: пикер и загрузка матчатся узко, отказ — нет", () => {
    expect(templateAskAction(ask(true), "Выбрать из «Файлов»")).toBe("picker");
    expect(templateAskAction(ask(true), "Загрузить документ")).toBe("upload");
    expect(templateAskAction(ask(true), "Продолжу без файла")).toBeNull();
    expect(templateAskAction(ask(true), "Ответить текстом")).toBeNull();
  });
});
