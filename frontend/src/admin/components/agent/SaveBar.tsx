type Props = { dirty: boolean; saving: boolean; savedBanner: boolean; onSave: () => void };

export function SaveBar({ dirty, saving, savedBanner, onSave }: Props) {
  return (
    <div className="agent-savebar">
      <button className="btn-primary" disabled={!dirty || saving} onClick={onSave}>
        {saving ? "Сохранение…" : "Сохранить"}
      </button>
      {dirty && !saving && <span className="savebar-hint">есть несохранённые изменения</span>}
      {savedBanner && (
        <span className="agent-banner">✓ Сохранено · применится после перезапуска агента</span>
      )}
    </div>
  );
}
