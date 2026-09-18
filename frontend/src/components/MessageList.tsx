import { useEffect, useRef } from "react";
import type { MessageAsk } from "../api/types";
import { useChat } from "../state/ChatContext";
import { AssistantMessage } from "./AssistantMessage";
import { ReviewRunCard } from "./review/ReviewRunCard";
import { UserMessage } from "./UserMessage";
import { WorkingIndicator } from "./WorkingIndicator";

// lastReviewRequest.label is built by DocumentChip as
// `Проверить «${filename}»: ${playbookName}` — pull the playbook name out
// for the run card's title; if the format doesn't match (future callers,
// tests), fall back to showing the whole label rather than nothing.
function playbookNameFromLabel(label: string): string {
  const marker = "»: ";
  const idx = label.indexOf(marker);
  return idx === -1 ? label : label.slice(idx + marker.length);
}

// E20: перехват работает ТОЛЬКО для ask'ов с признаком template (агент
// помечает вопросы шаблонного хода — ревью T-0137): «…из „Файлов“» открывает
// пикер, вариант, начинающийся с «Загрузить», — выбор файла в композере;
// остальное (включая отказы вроде «Продолжу без файла») уходит обычным
// ответом. Паттерны узкие: точный текст кнопок пишет LLM по промпту.
export function templateAskAction(ask: MessageAsk, option: string): "picker" | "upload" | null {
  if (!ask.template) return null;
  const lower = option.toLowerCase();
  if (lower.includes("файлов")) return "picker";
  if (lower.startsWith("загрузить")) return "upload";
  return null;
}

export function MessageList() {
  const {
    state,
    sendReview,
    answerAsk,
    focusComposer,
    openReviewPanel,
    send,
    openFilePicker,
    requestFileUpload,
    openFileReader,
  } = useChat();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "auto" });
  }, [state.messages, state.draftAnswer, state.working?.label, state.reviewProgress]);

  const reviewRequestDoc = state.lastReviewRequest
    ? state.documents.find((d) => d.id === state.lastReviewRequest?.documentId)
    : undefined;

  return (
    <div className="messages">
      <div className="messages-col">
        {state.messages.map((m, i) => {
          if (m.role === "user") return <UserMessage key={m.id} message={m} />;
          const ask = m.ask ?? null;
          // T-0046: an ask (question or persisted failure) only stays
          // actionable on the very last message, and only while nothing is
          // currently streaming — once the conversation moves on, the
          // buttons render disabled (AskBlock's `active`).
          const active = i === state.messages.length - 1 && !state.streaming;
          const doc = state.documents.find(
            (d) => d.id === (m.review?.document_id ?? ask?.document_id),
          );
          const onAskPick =
            ask?.kind === "review_role"
              ? (text: string) => void answerAsk(ask, text)
              : ask?.kind === "ask_user"
                ? (text: string) => {
                    const action = templateAskAction(ask, text);
                    if (action === "picker") openFilePicker("ask");
                    else if (action === "upload") requestFileUpload();
                    else void send(text);
                  }
                : undefined;
          const onAskRetry =
            ask?.kind === "review_failed"
              ? () => {
                  const failDoc = state.documents.find((d) => d.id === ask.document_id);
                  // The persisted ask doesn't carry a playbook display name
                  // (only its id) — fall back to a generic retry label
                  // rather than a wrong or missing one.
                  const label = failDoc ? `Проверить «${failDoc.filename}»` : "Повторить проверку";
                  void sendReview(ask.document_id ?? "", ask.playbook_id ?? "", label, ask.role ?? undefined);
                }
              : undefined;
          return (
            <AssistantMessage
              key={m.id}
              content={m.content}
              citations={m.citations}
              webSources={m.web_sources}
              review={m.review}
              ask={ask}
              actNames={state.acts}
              stopped={m.stopped ?? false}
              createdAt={m.created_at}
              messageId={m.id}
              doc={doc}
              onOpenReview={openReviewPanel}
              askActive={active}
              onAskPick={onAskPick}
              onAskFree={
                ask?.kind === "review_role" || ask?.kind === "ask_user" ? focusComposer : undefined
              }
              onAskRetry={onAskRetry}
              templateDraft={m.template_draft}
              templateDoc={m.template_doc}
              onOpenDocument={openFileReader}
            />
          );
        })}
        {state.pendingUser && <UserMessage message={state.pendingUser} />}
        {state.streaming && state.reviewProgress && (
          <ReviewRunCard
            state="progress"
            playbookName={
              state.lastReviewRequest ? playbookNameFromLabel(state.lastReviewRequest.label) : ""
            }
            doc={reviewRequestDoc}
            progress={state.reviewProgress}
            role={state.lastReviewRequest?.role}
          />
        )}
        {!state.streaming && state.reviewFailed && state.lastReviewRequest && (
          <ReviewRunCard
            state="failed"
            playbookName={playbookNameFromLabel(state.lastReviewRequest.label)}
            doc={reviewRequestDoc}
            detail={state.reviewFailed.detail}
            role={state.lastReviewRequest.role}
            onRetry={() => {
              const req = state.lastReviewRequest;
              if (req) void sendReview(req.documentId, req.playbookId, req.label, req.role ?? undefined);
            }}
          />
        )}
        {state.working && !state.reviewProgress && <WorkingIndicator label={state.working.label} />}
        {state.streaming && (state.draftAnswer || state.draftTemplateDraft || state.draftTemplateDoc) && (
          <AssistantMessage
            content={state.draftAnswer}
            citations={state.draftCitations}
            webSources={state.draftWebSources}
            review={state.draftReview}
            actNames={state.acts}
            templateDraft={state.draftTemplateDraft}
            templateDoc={state.draftTemplateDoc}
            onOpenDocument={openFileReader}
            streaming
          />
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
