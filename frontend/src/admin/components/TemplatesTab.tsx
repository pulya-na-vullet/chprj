import { Download, UploadCloud, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  createTemplate,
  deleteTemplate,
  listTemplates,
  patchTemplate,
  replaceTemplateFile,
  templateFileUrl,
} from "../api";
import type { AdminTemplateOut, TemplateField, TemplateFieldKind } from "../types";
import { formatDate, slugify } from "../util";
import { AdminModal } from "./AdminModal";

const KIND_LABEL: Record<TemplateFieldKind, string> = {
  text: "текст",
  date: "дата",
  money: "сумма",
  number: "число",
};

/** Стартовый набор для пустой библиотеки; живые категории добавляются из
 * уже загруженных шаблонов. Свободного ввода нет — «Договоры»/«Договора»
 * от опечатки не должны становиться разными разделами витрины. */
const PRESET_CATEGORIES = ["Договоры", "Доверенности", "Расписки", "Заявления"];
const NEW_CATEGORY = "__new__";

function describeError(err: unknown): string {
  if (err instanceof ApiError && err.status === 502) {
    return "Сервис шаблонов недоступен. Повторите позже.";
  }
  if (err instanceof ApiError && err.status === 409) {
    return "Шаблон с таким названием уже есть.";
  }
  const detail = err instanceof Error ? err.message : String(err);
  return `Не удалось выполнить операцию: ${detail}`;
}

/** Категория: выбор из существующих + пресеты; новая — только через явный
 * пункт, чтобы дубли не плодились от опечаток. */
function CategoryPicker({
  value,
  categories,
  disabled,
  onChange,
}: {
  value: string;
  categories: string[];
  disabled?: boolean;
  onChange: (v: string) => void;
}) {
  const [isNew, setIsNew] = useState(false);
  const options = Array.from(
    new Set([...categories, ...PRESET_CATEGORIES, ...(!isNew && value ? [value] : [])]),
  );
  if (isNew) {
    return (
      <span className="cat-new">
        <input
          autoFocus
          value={value}
          placeholder="Название категории"
          required
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
        <button
          type="button"
          className="btn-ghost"
          disabled={disabled}
          onClick={() => {
            setIsNew(false);
            onChange(options[0] ?? "");
          }}
        >
          К списку
        </button>
      </span>
    );
  }
  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => {
        if (e.target.value === NEW_CATEGORY) {
          setIsNew(true);
          onChange("");
        } else {
          onChange(e.target.value);
        }
      }}
    >
      {options.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
      <option value={NEW_CATEGORY}>+ Новая категория…</option>
    </select>
  );
}

/** Загрузка нового шаблона: .docx + метаданные; поля сканируются сервисом.
 * Slug оператор не вводит: он генерируется из названия, коллизия 409
 * разрешается автосуффиксом -2…-5. */
function UploadTemplateModal({
  categories,
  onClose,
  onDone,
}: {
  categories: string[];
  onClose: () => void;
  onDone: (created: AdminTemplateOut) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState(categories[0] ?? PRESET_CATEGORIES[0]);
  const [description, setDescription] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = (f: File | null) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".docx")) {
      setError("Нужен файл .docx");
      return;
    }
    setError(null);
    setFile(f);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Выберите файл .docx");
      return;
    }
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("title", title);
    form.append("category", category);
    form.append("description", description);
    const base = slugify(title);
    for (let attempt = 0; attempt < 5; attempt++) {
      const stem = base.slice(0, 61).replace(/-+$/, "");
      form.set("slug", attempt === 0 ? base : `${stem}-${attempt + 1}`);
      try {
        onDone(await createTemplate(form));
        return;
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) continue;
        setError(describeError(err));
        setBusy(false);
        return;
      }
    }
    setError("Шаблон с таким названием уже есть — измените название.");
    setBusy(false);
  };

  return (
    <AdminModal title="Добавить шаблон" onClose={onClose} closeOnBackdrop={!busy}>
      <p className="modal-text">
        Плейсхолдеры {"{{ … }}"} будут просканированы автоматически; подписи и типы полей
        заполните в карточке шаблона.
      </p>
      <form onSubmit={(e) => void submit(e)}>
        <div
          className={`dropzone ${dragOver ? "dropzone-active" : ""}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            pick(e.dataTransfer.files[0] ?? null);
          }}
        >
          <UploadCloud size={18} />
          <div>{file ? file.name : "Перетащите .docx или кликните для выбора"}</div>
          <input
            ref={inputRef}
            type="file"
            accept=".docx"
            hidden
            data-testid="template-file-input"
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
          />
        </div>
        <div className="form-grid">
          <label>
            Название
            <input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </label>
          <label>
            Категория
            <CategoryPicker
              value={category}
              categories={categories}
              disabled={busy}
              onChange={setCategory}
            />
          </label>
          <label>
            Описание
            <input value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
        </div>
        {error && <p className="error-text">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Загрузка…" : "Создать"}
          </button>
        </div>
      </form>
    </AdminModal>
  );
}

function DeleteTemplateDialog({
  template,
  busy,
  error,
  onClose,
  onConfirm,
}: {
  template: AdminTemplateOut;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <AdminModal title={`Удалить «${template.title}»?`} onClose={onClose} closeOnBackdrop={!busy}>
      <p className="modal-text">
        Шаблон и его .docx-файл будут удалены навсегда. Начатые в чате заполнения перестанут
        рендериться.
      </p>
      {error && <p className="error-text">{error}</p>}
      <div className="modal-actions">
        <button className="btn-ghost" disabled={busy} onClick={onClose}>
          Отмена
        </button>
        <button className="btn-primary" disabled={busy} onClick={onConfirm}>
          {busy ? "Удаление…" : "Удалить"}
        </button>
      </div>
    </AdminModal>
  );
}

/** Карточка шаблона: метаданные, таблица полей, публикация, замена файла. */
function TemplateDrawer({
  template,
  categories,
  onClose,
  onChanged,
  onDeleteRequest,
}: {
  template: AdminTemplateOut;
  categories: string[];
  onClose: () => void;
  onChanged: (t: AdminTemplateOut, notice?: string) => void;
  onDeleteRequest: (t: AdminTemplateOut) => void;
}) {
  const [title, setTitle] = useState(template.title);
  const [category, setCategory] = useState(template.category);
  const [description, setDescription] = useState(template.description);
  const [fields, setFields] = useState<TemplateField[]>(template.fields);
  const [orphaned, setOrphaned] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const patchField = (i: number, patch: Partial<TemplateField>) => {
    setFields((cur) => cur.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  };

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  };

  const save = () => {
    // В drawer нет <form>, так что required на вводе новой категории не
    // сработает — валидируем руками до похода на сервер (ревью T-0140).
    if (!category.trim()) {
      setError("Категория не может быть пустой.");
      return Promise.resolve();
    }
    return run(async () => {
      const updated = await patchTemplate(template.slug, {
        title,
        category,
        description,
        fields,
      });
      setFields(updated.fields);
      onChanged(updated, "Изменения сохранены.");
    });
  };

  const togglePublish = () =>
    run(async () => {
      const next = template.status === "published" ? "draft" : "published";
      const updated = await patchTemplate(template.slug, { status: next });
      onChanged(
        updated,
        next === "published" ? "Шаблон опубликован." : "Шаблон снят с публикации.",
      );
    });

  const replaceFile = (file: File) =>
    run(async () => {
      const form = new FormData();
      form.append("file", file);
      const resp = await replaceTemplateFile(template.slug, form);
      setFields(resp.template.fields);
      setOrphaned(new Set(resp.orphaned));
      const parts = [
        resp.added.length ? `новые поля: ${resp.added.join(", ")}` : null,
        resp.orphaned.length ? `нет в файле: ${resp.orphaned.join(", ")}` : null,
      ].filter(Boolean);
      onChanged(resp.template, `Файл заменён${parts.length ? ` — ${parts.join("; ")}` : ""}.`);
    });

  const dropField = (name: string) => {
    setFields((cur) => cur.filter((f) => f.name !== name));
    setOrphaned((cur) => {
      const next = new Set(cur);
      next.delete(name);
      return next;
    });
  };

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <aside className="drawer">
        <div className="drawer-head">
          <div>
            <div className="drawer-title">{template.title}</div>
            <div className="tpl-slug">{template.slug}</div>
          </div>
          <button className="btn-ghost" onClick={onClose} aria-label="Закрыть">
            <X size={16} />
          </button>
        </div>
        <div className="drawer-body">
          <div className="form-grid">
            <label>
              Название
              <input value={title} disabled={busy} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label>
              Категория
              <CategoryPicker
                value={category}
                categories={categories}
                disabled={busy}
                onChange={setCategory}
              />
            </label>
            <label>
              Описание
              <input
                value={description}
                disabled={busy}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
          </div>
          <div className="tpl-fields-head">
            Поля ({fields.length}) — подпись увидит пользователь в диалоге и сводке;
            техническое имя живёт только в .docx
          </div>
          {fields.map((f, i) => (
            <div key={f.name} className={`tpl-field ${orphaned.has(f.name) ? "tpl-orphan" : ""}`}>
              <div className="tpl-field-name">
                <code>{f.name}</code>
                {!orphaned.has(f.name) &&
                  (!f.label.trim() || f.label.trim() === f.name) && (
                    <span className="tpl-label-warn">подпись не задана</span>
                  )}
                {orphaned.has(f.name) && (
                  <span className="tpl-orphan-note">
                    нет в файле
                    <button
                      type="button"
                      className="btn-ghost"
                      disabled={busy}
                      onClick={() => dropField(f.name)}
                    >
                      Убрать
                    </button>
                  </span>
                )}
              </div>
              <div className="tpl-field-grid">
                <label>
                  Подпись
                  <input
                    value={f.label}
                    disabled={busy}
                    onChange={(e) => patchField(i, { label: e.target.value })}
                  />
                </label>
                <label>
                  Подсказка
                  <input
                    value={f.hint ?? ""}
                    disabled={busy}
                    onChange={(e) => patchField(i, { hint: e.target.value || null })}
                  />
                </label>
                <label>
                  Тип
                  <select
                    value={f.kind}
                    disabled={busy}
                    onChange={(e) => patchField(i, { kind: e.target.value as TemplateFieldKind })}
                  >
                    {(Object.keys(KIND_LABEL) as TemplateFieldKind[]).map((k) => (
                      <option key={k} value={k}>
                        {KIND_LABEL[k]}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={f.required}
                    disabled={busy}
                    onChange={(e) => patchField(i, { required: e.target.checked })}
                  />
                  Обязательное
                </label>
              </div>
            </div>
          ))}
          {error && <p className="error-text">{error}</p>}
          <div className="tpl-drawer-actions">
            <button className="btn-primary" disabled={busy} onClick={() => void save()}>
              {busy ? "Сохранение…" : "Сохранить"}
            </button>
            <button className="btn-row" disabled={busy} onClick={() => void togglePublish()}>
              {template.status === "published" ? "Снять с публикации" : "Опубликовать"}
            </button>
            <button
              className="btn-row"
              disabled={busy}
              onClick={() => fileRef.current?.click()}
            >
              Заменить файл
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".docx"
              hidden
              data-testid="replace-file-input"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void replaceFile(f);
                e.target.value = "";
              }}
            />
            <a className="btn-ghost" href={templateFileUrl(template.slug)} download>
              <Download size={14} /> Исходник
            </a>
            <button
              className="btn-row btn-row-danger"
              disabled={busy}
              onClick={() => onDeleteRequest(template)}
            >
              Удалить
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}

export function TemplatesTab() {
  const [templates, setTemplates] = useState<AdminTemplateOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<AdminTemplateOut | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listTemplates();
      setTemplates(data.templates);
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const applyChanged = useCallback((updated: AdminTemplateOut, message?: string) => {
    setTemplates((cur) => cur?.map((t) => (t.slug === updated.slug ? updated : t)) ?? cur);
    if (message) setNotice(message);
  }, []);

  const confirmDelete = useCallback(
    async (template: AdminTemplateOut) => {
      setDeleteBusy(true);
      setDeleteError(null);
      try {
        await deleteTemplate(template.slug);
        setDeleting(null);
        setSelectedSlug(null);
        setNotice(`Шаблон «${template.title}» удалён.`);
        await refresh();
      } catch (err) {
        setDeleteError(describeError(err));
      } finally {
        setDeleteBusy(false);
      }
    },
    [refresh],
  );

  const selected = templates?.find((t) => t.slug === selectedSlug) ?? null;
  const knownCategories = Array.from(new Set((templates ?? []).map((t) => t.category)));

  const head = (
    <div className="tpl-head-row">
      <div className="agent-head">
        <h2>Шаблоны</h2>
        <p>Библиотека .docx-шаблонов, которые агент заполняет в чате</p>
      </div>
      <button className="btn-primary" onClick={() => setUploadOpen(true)}>
        Добавить шаблон
      </button>
    </div>
  );

  if (!templates) {
    return (
      <div className="admin-shell">
        <div className="admin-main">
          {head}
          {error ? (
            <p className="error-text">{error}</p>
          ) : (
            <div className="users-skel" aria-hidden="true">
              {Array.from({ length: 4 }, (_, i) => (
                <div key={i} className="users-skel-row" />
              ))}
            </div>
          )}
        </div>
        {uploadOpen && (
          <UploadTemplateModal
            categories={knownCategories}
            onClose={() => setUploadOpen(false)}
            onDone={(created) => {
              setUploadOpen(false);
              setNotice(
                `Шаблон «${created.title}» создан черновиком — заполните поля и опубликуйте.`,
              );
              void refresh();
              setSelectedSlug(created.slug);
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="admin-shell">
      <div className="admin-main">
        {head}
        {notice && <p className="users-notice">{notice}</p>}
        {error && <p className="error-text">{error}</p>}
        {templates.length === 0 ? (
          <p className="empty-state">
            Шаблонов пока нет — загрузите первый .docx с {"{{ плейсхолдерами }}"}
          </p>
        ) : (
          <table className="doc-table">
            <thead>
              <tr>
                <th>Название</th>
                <th>Категория</th>
                <th className="num">Полей</th>
                <th>Статус</th>
                <th>Обновлён</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((t) => (
                <tr key={t.slug} className="tpl-row" onClick={() => setSelectedSlug(t.slug)}>
                  <td>
                    <div>{t.title}</div>
                    <div className="tpl-slug">{t.slug}</div>
                  </td>
                  <td>{t.category}</td>
                  <td className="num">{t.fields.length}</td>
                  <td className={t.status === "published" ? "" : "tpl-muted"}>
                    {t.status === "published" ? "Опубликован" : "Черновик"}
                  </td>
                  <td>{formatDate(t.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {selected && (
        <TemplateDrawer
          key={selected.slug}
          template={selected}
          categories={knownCategories}
          onClose={() => setSelectedSlug(null)}
          onChanged={applyChanged}
          onDeleteRequest={setDeleting}
        />
      )}
      {uploadOpen && (
        <UploadTemplateModal
          categories={knownCategories}
          onClose={() => setUploadOpen(false)}
          onDone={(created) => {
            setUploadOpen(false);
            setNotice(`Шаблон «${created.title}» создан черновиком — заполните поля и опубликуйте.`);
            void refresh();
            setSelectedSlug(created.slug);
          }}
        />
      )}
      {deleting && (
        <DeleteTemplateDialog
          template={deleting}
          busy={deleteBusy}
          error={deleteError}
          onClose={() => setDeleting(null)}
          onConfirm={() => void confirmDelete(deleting)}
        />
      )}
    </div>
  );
}
