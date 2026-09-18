import { notifyUnauthorized } from "./authEvents";
import type {
  Act,
  Conversation,
  HubDocumentContent,
  HubDocumentInfo,
  Message,
  PlaybookInfo,
  ReviewsResponse,
  Source,
  SourceArticleDetail,
  SourceArticleItem,
  TemplateSummary,
  UploadResponse,
} from "./types";

// Every user-facing route requires a session (T-0021); a 401 here means the
// cookie is gone or expired mid-session — not a per-call error the caller
// should render inline. Firing the global notifier lets `AuthContext` drop
// the whole app to the login screen in one place instead of every call site
// special-casing it.
function reportIfUnauthorized(resp: Response): void {
  if (resp.status === 401) notifyUnauthorized();
}

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  reportIfUnauthorized(resp);
  if (!resp.ok) throw new Error(`${url} → ${resp.status}`);
  return (await resp.json()) as T;
}

export async function listConversations(): Promise<Conversation[]> {
  const data = await getJson<{ conversations: Conversation[] }>("/conversations");
  return data.conversations;
}

export async function listReviews(): Promise<ReviewsResponse> {
  // Дефолтного limit=100 хватает MVP-объёмам; пагинация в UI появится
  // вместе с ростом данных (спека E07 §9).
  return getJson<ReviewsResponse>("/reviews");
}

export async function getMessages(id: string): Promise<Message[]> {
  const data = await getJson<{ messages: Message[] }>(
    `/conversations/${encodeURIComponent(id)}/messages`,
  );
  return data.messages;
}

export async function deleteConversation(id: string): Promise<void> {
  const resp = await fetch(`/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
  reportIfUnauthorized(resp);
  if (!resp.ok && resp.status !== 404) throw new Error(`delete → ${resp.status}`);
}

export async function stopChat(id: string): Promise<void> {
  const resp = await fetch(`/chat/${encodeURIComponent(id)}/stop`, { method: "POST" });
  reportIfUnauthorized(resp);
  if (!resp.ok && resp.status !== 404) throw new Error(`stop → ${resp.status}`);
}

export async function listActs(): Promise<Act[]> {
  const data = await getJson<{ acts: Act[] }>("/acts");
  return data.acts;
}

export async function listTemplates(): Promise<TemplateSummary[]> {
  const data = await getJson<{ templates: TemplateSummary[] }>("/templates");
  return data.templates;
}

export async function listSources(): Promise<Source[]> {
  const data = await getJson<{ sources: Source[] }>("/sources");
  return data.sources;
}

export async function getSourceArticles(sourceDocId: string): Promise<SourceArticleItem[]> {
  const data = await getJson<{ source_doc_id: string; short_name: string; articles: SourceArticleItem[] }>(
    `/sources/${encodeURIComponent(sourceDocId)}/articles`,
  );
  return data.articles;
}

export async function getArticleDetail(articleId: string): Promise<SourceArticleDetail> {
  return getJson<SourceArticleDetail>(`/sources/articles/${encodeURIComponent(articleId)}`);
}

export async function uploadDocument(
  file: File,
  sessionId: string | null,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (sessionId) form.append("session_id", sessionId);
  const resp = await fetch("/documents", { method: "POST", body: form });
  reportIfUnauthorized(resp);
  if (!resp.ok) {
    const detail = (await resp.json().catch(() => null))?.detail;
    throw new Error(typeof detail === "string" ? detail : `upload → ${resp.status}`);
  }
  return (await resp.json()) as UploadResponse;
}

export async function listPlaybooks(): Promise<PlaybookInfo[]> {
  const data = await getJson<{ playbooks: PlaybookInfo[] }>("/playbooks");
  return data.playbooks;
}

export async function getConversationDocuments(id: string): Promise<HubDocumentInfo[]> {
  const data = await getJson<{ documents: HubDocumentInfo[] }>(
    `/conversations/${encodeURIComponent(id)}/documents`,
  );
  return data.documents;
}

export async function getDocument(id: string): Promise<HubDocumentInfo> {
  return getJson<HubDocumentInfo>(`/documents/${encodeURIComponent(id)}`);
}

export async function getDocumentContent(id: string): Promise<HubDocumentContent> {
  return getJson<HubDocumentContent>(`/documents/${encodeURIComponent(id)}/content`);
}

export function documentDownloadUrl(id: string): string {
  return `/documents/${encodeURIComponent(id)}/download`;
}

export function reviewExportUrl(messageId: string): string {
  return `/reviews/${encodeURIComponent(messageId)}/export?format=docx`;
}

export async function listDocuments(): Promise<HubDocumentInfo[]> {
  const data = await getJson<{ documents: HubDocumentInfo[] }>("/library/documents");
  return data.documents;
}

export async function deleteDocument(id: string): Promise<void> {
  const resp = await fetch(`/library/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
  reportIfUnauthorized(resp);
  // 404 → already gone; treat as success (mirrors deleteConversation).
  if (!resp.ok && resp.status !== 404) throw new Error(`delete → ${resp.status}`);
}

export async function attachLibraryDocument(
  id: string,
  sessionId: string | null,
): Promise<UploadResponse> {
  const resp = await fetch(`/library/documents/${encodeURIComponent(id)}/attach`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!resp.ok) {
    const detail = (await resp.json().catch(() => null))?.detail;
    throw new Error(typeof detail === "string" ? detail : `attach → ${resp.status}`);
  }
  return (await resp.json()) as UploadResponse;
}

export async function uploadLibraryDocument(file: File): Promise<HubDocumentInfo> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch("/library/documents", { method: "POST", body: form });
  reportIfUnauthorized(resp);
  if (!resp.ok) {
    const detail = (await resp.json().catch(() => null))?.detail;
    throw new Error(typeof detail === "string" ? detail : `upload → ${resp.status}`);
  }
  return (await resp.json()) as HubDocumentInfo;
}
