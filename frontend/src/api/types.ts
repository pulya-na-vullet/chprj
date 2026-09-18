import type { components as AgentComponents } from "./generated/agent";
import type { components as RagComponents } from "./generated/rag";

// Public re-exports drive every consumer (state, components, sse). When the
// backend changes, regenerate generated/*.ts and these aliases pick up the
// new shape — or the type test in `test/types.test.ts` fails.
export type Act = RagComponents["schemas"]["ActSummary"];
export type Citation = AgentComponents["schemas"]["Citation"];
export type WebSource = AgentComponents["schemas"]["WebSource"];
export type Conversation = AgentComponents["schemas"]["ConversationOut"];
export type Message = AgentComponents["schemas"]["MessageOut"];
export type FoundArticle = AgentComponents["schemas"]["FoundArticle"];
export type Source = AgentComponents["schemas"]["SourceSummary"];
export type SourceArticleItem = AgentComponents["schemas"]["SourceArticleListItem"];
export type SourceArticleDetail = AgentComponents["schemas"]["SourceArticleDetail"];
export type HubDocumentInfo = AgentComponents["schemas"]["HubDocumentInfo"];
export type HubDocumentContent = AgentComponents["schemas"]["HubDocumentContent"];
export type HubSection = AgentComponents["schemas"]["HubSection"];
export type UploadResponse = AgentComponents["schemas"]["UploadResponse"];
export type PlaybookInfo = AgentComponents["schemas"]["PlaybookInfo"];
export type ReviewReport = AgentComponents["schemas"]["ReviewReportData"];
export type ReviewListItem = AgentComponents["schemas"]["ReviewListItem"];
export type ReviewsResponse = AgentComponents["schemas"]["ReviewsResponse"];
export type ReviewProgress = AgentComponents["schemas"]["ReviewProgressEventData"];
export type ReviewRisk = AgentComponents["schemas"]["ReviewRisk"];
export type ReviewCoverageItem = AgentComponents["schemas"]["ReviewCoverageItem"];
export type MessageAsk = AgentComponents["schemas"]["MessageAsk"];
export type AskEventData = AgentComponents["schemas"]["AskEventData"];
export type LoginRequest = AgentComponents["schemas"]["LoginRequest"];
export type RegisterRequest = AgentComponents["schemas"]["RegisterRequest"];
export type MeResponse = AgentComponents["schemas"]["MeResponse"];
export type TemplateSummary = AgentComponents["schemas"]["TemplateSummary"];
export type TemplateDraftData = AgentComponents["schemas"]["TemplateDraftEventData"];
export type DocumentReadyData = AgentComponents["schemas"]["DocumentReadyEventData"];
export type ProfileUpdateRequest = AgentComponents["schemas"]["ProfileUpdateRequest"];

export type Role = Message["role"];

// Mirrors ChatRequest.message max_length in src/neurolegal/contracts/chat.py.
// Enforced client-side so an oversize paste is caught before the 422.
export const MAX_MESSAGE_CHARS = 2000;

// SSE events are not part of the OpenAPI document (sse-starlette doesn't
// emit them). They are typed by hand against the matching `*EventData`
// schemas the backend exports.
export type ServerEvent =
  | { event: "session"; data: AgentComponents["schemas"]["SessionEventData"] }
  | { event: "reasoning"; data: AgentComponents["schemas"]["ReasoningEventData"] }
  | { event: "tool_call"; data: AgentComponents["schemas"]["ToolCallEventData"] }
  | { event: "tool_result"; data: AgentComponents["schemas"]["ToolResultEventData"] }
  | { event: "delta"; data: AgentComponents["schemas"]["DeltaEventData"] }
  | { event: "reset_delta"; data: AgentComponents["schemas"]["ResetDeltaEventData"] }
  | { event: "citations"; data: AgentComponents["schemas"]["CitationsEventData"] }
  | { event: "web_sources"; data: AgentComponents["schemas"]["WebSourcesEventData"] }
  | { event: "review_progress"; data: ReviewProgress }
  | { event: "review_report"; data: ReviewReport }
  | { event: "template_draft"; data: TemplateDraftData }
  | { event: "document_ready"; data: DocumentReadyData }
  | { event: "ask"; data: AskEventData }
  | { event: "done"; data: AgentComponents["schemas"]["DoneEventData"] }
  | { event: "error"; data: AgentComponents["schemas"]["ErrorEventData"] };
