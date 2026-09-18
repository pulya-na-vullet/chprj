import type {
  AdminArticleDetail,
  AdminArticlesResponse,
  AdminDocumentsResponse,
  AdminTemplateOut,
  AdminTemplatePatchRequest,
  AdminTemplatesResponse,
  AdminUserOut,
  AdminUsersResponse,
  AgentPromptDefaults,
  AgentSettings,
  DeleteDocumentRequest,
  IndexesStatusResponse,
  IngestAccepted,
  JobsResponse,
  ManifestUpdateRequest,
  OpenRouterModelsResponse,
  SearchResponse,
  TemplateFileReplaceResponse,
  UploadDocumentResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body: unknown = await resp.json();
      if (body && typeof body === "object" && "detail" in body) {
        detail = String((body as { detail: unknown }).detail);
      }
    } catch {
      // non-JSON error body — keep the bare status
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

const json = (body: unknown): Pick<RequestInit, "headers" | "body"> => ({
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const listDocuments = () => request<AdminDocumentsResponse>("/admin/documents");

export const startIngest = (codeId: string) =>
  request<IngestAccepted>("/admin/ingest", { method: "POST", ...json({ code_id: codeId }) });

export const listJobs = () => request<JobsResponse>("/admin/jobs");

export const cancelJob = (jobId: string) =>
  request<{ status: string }>(`/admin/jobs/${jobId}/cancel`, { method: "POST" });

export const deleteDocument = (codeId: string, opts: DeleteDocumentRequest) =>
  request<{ status: string }>(`/admin/documents/${encodeURIComponent(codeId)}`, {
    method: "DELETE",
    ...json(opts),
  });

export const updateManifest = (codeId: string, req: ManifestUpdateRequest) =>
  request<{ status: string }>(`/admin/documents/${encodeURIComponent(codeId)}/manifest`, {
    method: "PUT",
    ...json(req),
  });

export const uploadDocument = (form: FormData) =>
  request<UploadDocumentResponse>("/admin/documents", { method: "POST", body: form });

export const listArticles = (codeId: string) =>
  request<AdminArticlesResponse>(`/admin/documents/${encodeURIComponent(codeId)}/articles`);

export const getArticle = (articleId: string) =>
  request<AdminArticleDetail>(`/admin/articles/${articleId}`);

export const runSearch = (q: string, acts: string[], limit: number) => {
  const params = new URLSearchParams({ q, limit: String(limit) });
  for (const a of acts) params.append("acts", a);
  return request<SearchResponse>(`/search?${params.toString()}`);
};

export const getIndexes = () => request<IndexesStatusResponse>("/admin/indexes");

export const getHealth = () => request<{ status: string; db: string }>("/healthz");

export const getAgentSettings = () => request<AgentSettings>("/admin/agent/settings");

export const saveAgentSettings = (s: AgentSettings) =>
  request<{ status: string }>("/admin/agent/settings", { method: "PUT", ...json(s) });

export const listOpenRouterModels = () =>
  request<OpenRouterModelsResponse>("/admin/agent/models");

export const getAgentDefaults = () => request<AgentPromptDefaults>("/admin/agent/defaults");

export const listUsers = () => request<AdminUsersResponse>("/admin/users");

export const setUserActive = (userId: string, isActive: boolean) =>
  request<AdminUserOut>(`/admin/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    ...json({ is_active: isActive }),
  });

/** Operator password reset (T-0026) — drops all of the user's sessions. */
export const resetUserPassword = (userId: string, newPassword: string) =>
  request<AdminUserOut>(`/admin/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    ...json({ new_password: newPassword }),
  });

export const listTemplates = () => request<AdminTemplatesResponse>("/admin/templates");

export const createTemplate = (form: FormData) =>
  request<AdminTemplateOut>("/admin/templates", { method: "POST", body: form });

export const patchTemplate = (slug: string, req: AdminTemplatePatchRequest) =>
  request<AdminTemplateOut>(`/admin/templates/${encodeURIComponent(slug)}`, {
    method: "PATCH",
    ...json(req),
  });

export const replaceTemplateFile = (slug: string, form: FormData) =>
  request<TemplateFileReplaceResponse>(`/admin/templates/${encodeURIComponent(slug)}/file`, {
    method: "PUT",
    body: form,
  });

/** DELETE отвечает 204 без тела — общий request() тут не годится. */
export const deleteTemplate = async (slug: string): Promise<void> => {
  const resp = await fetch(`/admin/templates/${encodeURIComponent(slug)}`, { method: "DELETE" });
  if (!resp.ok) throw new ApiError(resp.status, `HTTP ${resp.status}`);
};

/** Ссылка для скачивания исходника — открывается браузером напрямую. */
export const templateFileUrl = (slug: string) =>
  `/admin/templates/${encodeURIComponent(slug)}/file`;
