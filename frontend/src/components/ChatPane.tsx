import { useChat } from "../state/ChatContext";
import { Composer } from "./Composer";
import { HomeState } from "./HomeState";
import { MessageList } from "./MessageList";
import { ReviewPanel } from "./review/ReviewPanel";
import { FilePickerModal } from "./templates/FilePickerModal";

export function ChatPane() {
  const { state, send, setBanner, attachFromLibrary, closeFilePicker } = useChat();
  const empty = state.messages.length === 0 && !state.pendingUser && !state.streaming;
  const panelMsg = state.reviewPanelFor
    ? state.messages.find((m) => m.id === state.reviewPanelFor)
    : undefined;

  // E20: пикер «Из моих файлов». Из ask-кнопки (source="ask") после
  // приложения уходит ответное сообщение — агент продолжает диалог и читает
  // документ; из меню скрепки достаточно чипа в композере.
  const pickerSource = state.filePicker;
  const onPickDocument = async (docId: string, filename: string) => {
    closeFilePicker();
    try {
      await attachFromLibrary(docId);
    } catch {
      setBanner("Не удалось приложить документ. Попробуйте ещё раз.");
      return;
    }
    if (pickerSource === "ask") {
      void send(`Приложил документ «${filename}» — возьмите реквизиты из него`);
    }
  };

  return (
    <main className="chat-canvas">
      <div className="chat-win">
        {state.banner && <div className="banner">{state.banner}</div>}
        {empty ? <HomeState /> : <MessageList />}
        {!empty && <Composer />}
        {panelMsg && <ReviewPanel message={panelMsg} />}
        {pickerSource && (
          <FilePickerModal
            onClose={closeFilePicker}
            onPick={(doc) => void onPickDocument(doc.id, doc.filename)}
          />
        )}
      </div>
    </main>
  );
}
