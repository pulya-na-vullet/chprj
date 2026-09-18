import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

import { AssistantMessage } from "../components/AssistantMessage";
import { ReviewRunCard } from "../components/review/ReviewRunCard";
import type { HubDocumentInfo, MessageAsk, ReviewProgress, ReviewReport, ReviewRisk } from "../api/types";

function risk(over: Partial<ReviewRisk> = {}): ReviewRisk {
  return {
    citations: [],
    contract_quote: "",
    explanation: "",
    level: "medium",
    no_basis: false,
    recommendation: "",
    rule_id: "r1",
    section_number: null,
    title: "Риск",
    verdict: "confirmed",
    ...over,
  };
}

function report(over: Partial<ReviewReport> = {}): ReviewReport {
  return {
    coverage: [],
    disclaimer: "Черновая проверка",
    document_id: "d1",
    playbook_id: "supply_ru",
    playbook_name: "Договор поставки",
    risks: [],
    ...over,
  };
}

function doc(over: Partial<HubDocumentInfo> = {}): HubDocumentInfo {
  return {
    id: "d1",
    owner_id: "default",
    filename: "договор.pdf",
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

describe("ReviewRunCard", () => {
  it("done-карточка: счётчики уровней и открытие панели", () => {
    const onOpen = vi.fn();
    const r = report({
      risks: [
        risk({ level: "high", rule_id: "r1" }),
        risk({ level: "high", rule_id: "r2" }),
        risk({ level: "medium", rule_id: "r3" }),
      ],
    });
    render(<ReviewRunCard state="done" report={r} doc={doc()} onOpen={onOpen} />);
    expect(screen.getByText(/Высокий/)).toHaveTextContent("Высокий 2");
    expect(screen.getByText(/Средний/)).toHaveTextContent("Средний 1");
    expect(screen.queryByText(/Низкий/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Открыть отчёт/ }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("progress-карточка: прогрессбар с ARIA и текущим правилом", () => {
    const progress: ReviewProgress = {
      index: 2,
      total: 12,
      rule_id: "r2",
      status: "running",
      title: "Неустойка",
    };
    render(<ReviewRunCard state="progress" playbookName="Договор поставки" progress={progress} />);
    const bar = screen.getByRole("progressbar", { name: "Прогресс проверки" });
    expect(bar).toHaveAttribute("aria-valuenow", "2");
    expect(bar).toHaveAttribute("aria-valuemax", "12");
    expect(screen.getByText(/2 из 12/)).toHaveTextContent("Неустойка");
  });

  it("failed-карточка: кнопка Повторить зовёт onRetry", () => {
    const onRetry = vi.fn();
    render(
      <ReviewRunCard
        state="failed"
        playbookName="Договор поставки"
        detail="Документ не найден"
        onRetry={onRetry}
      />,
    );
    expect(screen.getByText("Документ не найден")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Повторить/ }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("AssistantMessage с review не рендерит markdown-дубль", () => {
    const r = report({ risks: [risk({ level: "high" })] });
    render(
      <AssistantMessage
        content="# Проверка по плейбуку «Договор поставки»"
        citations={null}
        actNames={[]}
        review={r}
        messageId="m1"
        onOpenReview={vi.fn()}
      />,
    );
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.getByText(/Проверка завершена/)).toBeInTheDocument();
  });

  it("done-карточка: без роли и времени — только чип файла (T-0052)", () => {
    // Роль и время дублировали шапку панели и метку сообщения под карточкой
    // (замечание клиента в ревью эпика) — в done-карточке остаётся один чип.
    const withRole = report({ role: "Покупатель" });
    const { container } = render(
      <ReviewRunCard state="done" report={withRole} doc={doc()} onOpen={vi.fn()} />,
    );
    expect(container.querySelector(".rvc-run-card-s")).not.toHaveTextContent("вы —");
    expect(container.querySelector(".rvc-run-card-time")).toBeNull();
    expect(screen.getByText("договор.pdf")).toBeInTheDocument();
  });

  it("progress-карточка: показывает роль из lastReviewRequest, если известна (T-0046)", () => {
    const progress: ReviewProgress = {
      index: 2,
      total: 12,
      rule_id: "r2",
      status: "running",
      title: "Неустойка",
    };
    render(
      <ReviewRunCard
        state="progress"
        playbookName="Договор поставки"
        progress={progress}
        role="Покупатель"
      />,
    );
    expect(screen.getByText("вы — Покупатель")).toBeInTheDocument();
  });

  it("progress-карточка без имени плейбука показывает голое «Проверка» (T-0046)", () => {
    const progress: ReviewProgress = {
      index: 1,
      total: 5,
      rule_id: "r1",
      status: "running",
      title: "Правило",
    };
    render(<ReviewRunCard state="progress" playbookName="" progress={progress} />);
    expect(screen.getByText("Проверка")).toBeInTheDocument();
  });

  it("failed-карточка без имени плейбука показывает «Проверка не удалась» без разделителя (T-0046)", () => {
    render(
      <ReviewRunCard
        state="failed"
        playbookName=""
        detail="Документ не найден"
        onRetry={vi.fn()}
        role="Покупатель"
      />,
    );
    expect(screen.getByText("Проверка не удалась")).toBeInTheDocument();
    expect(screen.getByText("вы — Покупатель")).toBeInTheDocument();
  });

  it("AssistantMessage с review скрывает «Копировать ответ»", () => {
    const r = report({ risks: [] });
    render(
      <AssistantMessage
        content="Готово"
        citations={null}
        actNames={[]}
        review={r}
        messageId="m1"
        createdAt="2026-07-18T10:00:00"
        onOpenReview={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText("Копировать ответ")).toBeNull();
  });
});

function askRole(over: Partial<MessageAsk> = {}): MessageAsk {
  return {
    kind: "review_role",
    template: false,
    question: "Кто вы по этому договору?",
    options: ["Покупатель", "Поставщик"],
    ...over,
  };
}

describe("AssistantMessage ask (T-0046)", () => {
  it("ask.kind=review_role renders content as markdown, then AskBlock below — question isn't duplicated", () => {
    render(
      <AssistantMessage
        content="Кто вы по этому договору?"
        citations={null}
        actNames={[]}
        ask={askRole()}
        askActive
        onAskPick={vi.fn()}
        onAskFree={vi.fn()}
      />,
    );
    expect(screen.getByText("Кто вы по этому договору?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Покупатель" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Другое — напишу сам" })).toBeEnabled();
  });

  it("ask.kind=review_role, askActive=false — AskBlock buttons render disabled", () => {
    render(
      <AssistantMessage
        content="Кто вы по этому договору?"
        citations={null}
        actNames={[]}
        ask={askRole()}
        askActive={false}
      />,
    );
    expect(screen.getByRole("button", { name: "Покупатель" })).toBeDisabled();
  });

  it("onAskPick/onAskFree wire through to AskBlock", () => {
    const onAskPick = vi.fn();
    const onAskFree = vi.fn();
    render(
      <AssistantMessage
        content="Кто вы по этому договору?"
        citations={null}
        actNames={[]}
        ask={askRole()}
        askActive
        onAskPick={onAskPick}
        onAskFree={onAskFree}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Покупатель" }));
    expect(onAskPick).toHaveBeenCalledWith("Покупатель");
    fireEvent.click(screen.getByRole("button", { name: "Другое — напишу сам" }));
    expect(onAskFree).toHaveBeenCalledTimes(1);
  });

  it("ask.kind=review_failed renders a failed ReviewRunCard instead of markdown content", () => {
    const onAskRetry = vi.fn();
    render(
      <AssistantMessage
        content="Документ не найден в этой беседе"
        citations={null}
        actNames={[]}
        ask={askRole({
          kind: "review_failed",
          question: null,
          options: [],
          error: "Документ не найден в этой беседе",
          role: "Покупатель",
        })}
        onAskRetry={onAskRetry}
      />,
    );
    expect(screen.getByText("Документ не найден в этой беседе")).toBeInTheDocument();
    expect(screen.getByText("вы — Покупатель")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Повторить/ }));
    expect(onAskRetry).toHaveBeenCalledTimes(1);
  });

  it("ask.kind=review_failed hides the plain 'Копировать ответ' action", () => {
    render(
      <AssistantMessage
        content="Документ не найден"
        citations={null}
        actNames={[]}
        ask={askRole({ kind: "review_failed", error: "Документ не найден" })}
        createdAt="2026-07-18T10:00:00"
        onAskRetry={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText("Копировать ответ")).toBeNull();
  });
});
