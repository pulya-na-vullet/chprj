import type { HubDocumentInfo } from "../../api/types";

export function filterDocuments(docs: HubDocumentInfo[], query: string): HubDocumentInfo[] {
  const q = query.trim().toLowerCase();
  return q ? docs.filter((d) => d.filename.toLowerCase().includes(q)) : docs;
}
