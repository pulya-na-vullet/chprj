import { memo } from "react";
import type {
  Citation,
  DocumentReadyData,
  HubDocumentInfo,
  MessageAsk,
  ReviewReport,
  TemplateDraftData,
  WebSource,
} from "../api/types";
import { RenderMarkdown } from "../markdown/renderMarkdown";
import { formatTimestamp } from "../util/format";
import { CopyButton } from "./CopyButton";
import { ErrorBoundary } from "./ErrorBoundary";
import { AskBlock } from "./review/AskBlock";
import { ReviewRunCard } from "./review/ReviewRunCard";
import { TemplateDocCard } from "./templates/TemplateDocCard";
import { TemplateDraftCard } from "./templates/TemplateDraftCard";

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// memo matters here: every SSE delta re-renders MessageList, and re-parsing
// the markdown of all completed messages on each token causes visible jank.
// `actNames` comes in as a prop (not useChat) so the memo can actually hold.
export const AssistantMessage = memo(function AssistantMessage({
  content,
  citations,
  webSources,
  review,
  ask,
  actNames,
  streaming = false,
  stopped = false,
  createdAt,
  messageId,
  doc,
  onOpenReview,
  askActive = false,
  onAskPick,
  onAskFree,
  onAskRetry,
  templateDraft,
  templateDoc,
  onOpenDocument,
}: {
  content: string;
  citations: Citation[] | null;
  webSources?: WebSource[] | null;
  review?: ReviewReport | null;
  // T-0046: a paused risk_review question (kind "review_role") or a plain
  // clarifying question from any turn (kind "ask_user", T-0051) — both
  // rendered as AskBlock below the content — or a persisted review failure
  // (kind "review_failed", replacing content with a failed ReviewRunCard) —
  // replayed from the DB via MessageOut.ask, or folded into the finalized
  // message on FINISH_TURN (chatReducer's draftAsk).
  ask?: MessageAsk | null;
  actNames: string[];
  streaming?: boolean;
  stopped?: boolean;
  createdAt?: string | null;
  // Review-branch only: the finalized message id (to target OPEN_REVIEW_PANEL)
  // and the source document (for the run card's file chip). Both come from
  // MessageList, which already holds useChat state — keeping them as plain
  // props (not a useChat() call in here) preserves this component's memo:
  // every SSE delta re-renders MessageList, and re-subscribing to context
  // here would re-render every finalized message on each token.
  messageId?: string;
  doc?: HubDocumentInfo;
  onOpenReview?: (messageId: string) => void;
  // AskBlock props (review_role, ask_user): active is false once the
  // conversation has moved past this message (MessageList computes it: last
  // message + not streaming) — the buttons stay visible but disabled, since
  // the answer is now only meaningful as the very next message.
  askActive?: boolean;
  onAskPick?: (text: string) => void;
  onAskFree?: () => void;
  // Failed-run retry (review_failed), reconstructed from the persisted ask.
  onAskRetry?: () => void;
  // E20: карточки шаблонного флоу — сводка staged-черновика и готовый
  // документ; из стрима (draft*) или с сообщения (template_draft/_doc).
  templateDraft?: TemplateDraftData | null;
  templateDoc?: DocumentReadyData | null;
  onOpenDocument?: (documentId: string) => void;
}) {
  return (
    <div className={streaming ? "msg-assistant streaming" : "msg-assistant"}>
      {review ? (
        <ReviewRunCard
          state="done"
          report={review}
          doc={doc}
          onOpen={() => {
            if (messageId) onOpenReview?.(messageId);
          }}
        />
      ) : ask?.kind === "review_failed" ? (
        <ReviewRunCard
          state="failed"
          playbookName=""
          doc={doc}
          detail={ask.error || content}
          role={ask.role}
          onRetry={() => onAskRetry?.()}
        />
      ) : (
        <>
          {/* Карточки шаблонного хода — НАД текстом: stage/render случаются до
              пост-tool текста (reset_delta), и стрим дописывается вниз, а не
              печатается поверх уже показанной карточки (замечание клиента,
              T-0141). */}
          {templateDraft && <TemplateDraftCard data={templateDraft} />}
          {templateDoc && <TemplateDocCard data={templateDoc} onOpen={onOpenDocument} />}
          <ErrorBoundary resetKey={content} fallback={<div className="msg-plain">{content}</div>}>
            <RenderMarkdown content={content} citations={citations ?? []} actNames={actNames} />
          </ErrorBoundary>
          {(ask?.kind === "review_role" || ask?.kind === "ask_user") && (
            <AskBlock
              ask={ask}
              active={askActive}
              onPick={(text) => onAskPick?.(text)}
              onFree={() => onAskFree?.()}
            />
          )}
        </>
      )}
      {webSources && webSources.length > 0 && (
        <div className="web-sources">
          <div className="web-sources-title">Источники из интернета</div>
          <ul>
            {webSources.map((s) => (
              <li key={s.url}>
                <a href={s.url} target="_blank" rel="noopener noreferrer" title={s.url}>
                  {s.title || hostname(s.url)}
                </a>
                <span className="web-sources-host"> · {hostname(s.url)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {stopped && <div className="msg-stopped">Генерация остановлена</div>}
      {!streaming && (
        <div className="msg-actions">
          {createdAt && <span className="msg-time">{formatTimestamp(createdAt)}</span>}
          {/* The panel gives its own "Копировать отчёт" — a plain answer copy
              here would just duplicate that and copy nothing useful (content
              is the raw markdown the run card replaces). Same for a
              review_failed ask: content is the raw error text the failed
              run card already shows. */}
          {!review && ask?.kind !== "review_failed" && (
            <CopyButton text={content} label="Копировать ответ" />
          )}
        </div>
      )}
    </div>
  );
});
