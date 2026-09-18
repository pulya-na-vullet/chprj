import { useCallback, useEffect, useState } from "react";
import { ApiError, deleteDocument, getHealth, getIndexes, listDocuments, startIngest } from "./api";
import { AgentTab } from "./components/AgentTab";
import { type AdminSection, AppSidebar } from "./components/AppSidebar";
import { DeleteDialog } from "./components/DeleteDialog";
import { DocumentDrawer } from "./components/DocumentDrawer";
import { DocumentsTable } from "./components/DocumentsTable";
import { HeaderBar, type AdminTab, type HealthState } from "./components/HeaderBar";
import { JobBanner } from "./components/JobBanner";
import { SearchTab } from "./components/SearchTab";
import { TemplatesTab } from "./components/TemplatesTab";
import { UploadModal } from "./components/UploadModal";
import { UsersTab } from "./components/UsersTab";
import { useJobs } from "./hooks/useJobs";
import type { AdminDocument, DeleteDocumentRequest } from "./types";

export function App() {
  const [section, setSection] = useState<AdminSection>("sources");
  const [tab, setTab] = useState<AdminTab>("documents");
  const [docs, setDocs] = useState<AdminDocument[]>([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [dbSize, setDbSize] = useState(0);
  const [health, setHealth] = useState<HealthState | null>(null);
  const [selected, setSelected] = useState<AdminDocument | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [deleting, setDeleting] = useState<AdminDocument | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshDocuments = useCallback(async () => {
    try {
      const data = await listDocuments();
      setDocs(data.documents);
      setTotalChunks(data.total_chunks);
      setDbSize(data.db_size_bytes);
    } catch {
      setError("не удалось загрузить список документов — RAG-сервис доступен?");
    }
  }, []);

  const { jobs, active, refresh: refreshJobs } = useJobs(refreshDocuments);

  useEffect(() => {
    void refreshDocuments();
    void (async () => {
      try {
        const [h, idx] = await Promise.all([getHealth(), getIndexes()]);
        setHealth({ db: h.db === "ok", hnsw: idx.hnsw, gin: idx.gin });
      } catch {
        setHealth(null);
      }
    })();
  }, [refreshDocuments]);

  const handleIngest = useCallback(
    async (doc: AdminDocument) => {
      if (!doc.code_id) return;
      setError(null);
      try {
        await startIngest(doc.code_id);
        await refreshJobs();
        await refreshDocuments();
      } catch (err) {
        setError(
          err instanceof ApiError && err.status === 409
            ? "дождитесь завершения текущей задачи"
            : `загрузка не запустилась: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    },
    [refreshJobs, refreshDocuments],
  );

  const handleDelete = useCallback(
    async (doc: AdminDocument, opts: DeleteDocumentRequest) => {
      setError(null);
      try {
        await deleteDocument(doc.code_id ?? doc.source_doc_id, opts);
        setDeleting(null);
        setSelected(null);
        await refreshDocuments();
      } catch (err) {
        setError(`не удалось удалить: ${err instanceof Error ? err.message : String(err)}`);
      }
    },
    [refreshDocuments],
  );

  return (
    <div className="app">
      <AppSidebar section={section} onSection={setSection} />
      {section === "agent" ? (
        <AgentTab />
      ) : section === "users" ? (
        <UsersTab />
      ) : section === "templates" ? (
        <TemplatesTab />
      ) : (
        <div className="admin-shell">
          <HeaderBar
            tab={tab}
            onTab={setTab}
            health={health}
            onUpload={() => setUploadOpen(true)}
          />
          <main className="admin-main">
            <JobBanner jobs={jobs} active={active} onChanged={() => void refreshJobs()} />
            {error && <p className="error-text">{error}</p>}
            {tab === "documents" ? (
              <DocumentsTable
                documents={docs}
                totalChunks={totalChunks}
                dbSize={dbSize}
                jobRunning={active !== null}
                onSelect={setSelected}
                onIngest={(d) => void handleIngest(d)}
                onDelete={setDeleting}
              />
            ) : (
              <SearchTab documents={docs} />
            )}
          </main>
          {selected && (
            <DocumentDrawer
              doc={selected}
              jobRunning={active !== null}
              onClose={() => setSelected(null)}
              onIngest={(d) => void handleIngest(d)}
              onDelete={setDeleting}
              onManifestSaved={() => {
                setSelected(null);
                void refreshDocuments();
              }}
            />
          )}
          {uploadOpen && (
            <UploadModal
              onClose={() => setUploadOpen(false)}
              onDone={() => {
                setUploadOpen(false);
                void refreshJobs();
                void refreshDocuments();
              }}
            />
          )}
          {deleting && (
            <DeleteDialog
              doc={deleting}
              onClose={() => setDeleting(null)}
              onConfirm={(opts) => void handleDelete(deleting, opts)}
            />
          )}
        </div>
      )}
    </div>
  );
}
