import { useCallback, useEffect, useState } from "react";
import { ApiError, listUsers, resetUserPassword, setUserActive } from "../api";
import type { AdminUserOut } from "../types";
import { formatDate } from "../util";
import { AdminModal } from "./AdminModal";

const MIN_PASSWORD_LENGTH = 8;

function describeError(err: unknown): string {
  if (err instanceof ApiError && err.status === 502) {
    return "Агент недоступен. Повторите позже.";
  }
  const detail = err instanceof Error ? err.message : String(err);
  return `Не удалось выполнить операцию: ${detail}`;
}

/** Modal for the operator password reset (T-0026 — the only reset path in the
 * mail-less MVP). `busy`/`error` are owned by the parent so the request outcome
 * is visible over the overlay and the button locks while in flight (T-0035). */
function ResetPasswordDialog({
  user,
  busy,
  error,
  onClose,
  onConfirm,
}: {
  user: AdminUserOut;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: (newPassword: string) => void;
}) {
  const [password, setPassword] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = () => {
    if (password.length < MIN_PASSWORD_LENGTH) {
      setLocalError(`Пароль должен быть не короче ${MIN_PASSWORD_LENGTH} символов`);
      return;
    }
    onConfirm(password);
  };

  return (
    <AdminModal
      title={`Сбросить пароль для ${user.email}?`}
      onClose={onClose}
      closeOnBackdrop={!busy}
    >
      <p className="modal-text">
        Все открытые сессии пользователя будут завершены. Передайте новый пароль пользователю —
        письмо не отправляется.
      </p>
      <form
        className="form-grid"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label>
          Новый пароль
          <input
            type="text"
            autoFocus
            autoComplete="off"
            disabled={busy}
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              setLocalError(null);
            }}
          />
        </label>
      </form>
      {(localError ?? error) && <p className="error-text">{localError ?? error}</p>}
      <div className="modal-actions">
        <button className="btn-ghost" disabled={busy} onClick={onClose}>
          Отмена
        </button>
        <button className="btn-primary" disabled={busy} onClick={submit}>
          {busy ? "Сохранение…" : "Сохранить"}
        </button>
      </div>
    </AdminModal>
  );
}

/** Block confirmation (T-0035): blocking drops every session, so it gets the
 * same explicit gate the password reset has. Unblock stays a one-click action. */
function BlockDialog({
  user,
  busy,
  error,
  onClose,
  onConfirm,
}: {
  user: AdminUserOut;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <AdminModal title={`Заблокировать ${user.email}?`} onClose={onClose} closeOnBackdrop={!busy}>
      <p className="modal-text">
        Пользователь потеряет доступ к сервису, все его открытые сессии будут завершены. Доступ
        можно вернуть кнопкой «Разблокировать».
      </p>
      {error && <p className="error-text">{error}</p>}
      <div className="modal-actions">
        <button className="btn-ghost" disabled={busy} onClick={onClose}>
          Отмена
        </button>
        <button className="btn-primary" disabled={busy} onClick={onConfirm}>
          {busy ? "Блокировка…" : "Заблокировать"}
        </button>
      </div>
    </AdminModal>
  );
}

export function UsersTab() {
  const [users, setUsers] = useState<AdminUserOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [resetUser, setResetUser] = useState<AdminUserOut | null>(null);
  const [blockUser, setBlockUser] = useState<AdminUserOut | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listUsers();
      setUsers(data.users);
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const applyActive = useCallback(async (user: AdminUserOut, active: boolean) => {
    setPendingId(user.id);
    setDialogError(null);
    setNotice(null);
    try {
      const updated = await setUserActive(user.id, active);
      setUsers((cur) => cur?.map((u) => (u.id === updated.id ? updated : u)) ?? cur);
      setBlockUser(null);
      setNotice(
        active
          ? `${user.email} разблокирован.`
          : `${user.email} заблокирован. Открытые сессии завершены.`,
      );
    } catch (err) {
      setDialogError(describeError(err));
    } finally {
      setPendingId(null);
    }
  }, []);

  const confirmReset = useCallback(async (user: AdminUserOut, newPassword: string) => {
    setPendingId(user.id);
    setDialogError(null);
    setNotice(null);
    try {
      await resetUserPassword(user.id, newPassword);
      setResetUser(null);
      setNotice(`Пароль обновлён для ${user.email}. Открытые сессии завершены.`);
    } catch (err) {
      setDialogError(describeError(err));
    } finally {
      setPendingId(null);
    }
  }, []);

  if (error && !users) {
    return (
      <div className="admin-shell">
        <div className="admin-main">
          <div className="agent-head">
            <h2>Пользователи</h2>
            <p>Операторское управление доступом к сервису</p>
          </div>
          <p className="error-text">{error}</p>
        </div>
      </div>
    );
  }

  if (!users) {
    return (
      <div className="admin-shell">
        <div className="admin-main">
          <div className="agent-head">
            <h2>Пользователи</h2>
            <p>Операторское управление доступом к сервису</p>
          </div>
          <div className="users-skel" aria-hidden="true">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="users-skel-row" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-shell">
      <div className="admin-main">
        <div className="agent-head">
          <h2>Пользователи</h2>
          <p>Операторское управление доступом к сервису</p>
        </div>
        {notice && <p className="users-notice">{notice}</p>}
        {error && <p className="error-text">{error}</p>}
        {users.length === 0 ? (
          <p className="empty-state">Пользователей пока нет</p>
        ) : (
          <table className="doc-table">
            <thead>
              <tr>
                <th>Почта</th>
                <th>Статус</th>
                <th>Регистрация</th>
                <th className="num">Бесед</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>{u.is_active ? "Активен" : "Заблокирован"}</td>
                  <td>{formatDate(u.created_at)}</td>
                  <td className="num">{u.conversation_count}</td>
                  <td>
                    <div className="row-actions">
                      <button
                        type="button"
                        className="btn-row"
                        disabled={pendingId === u.id}
                        onClick={() => {
                          setDialogError(null);
                          setResetUser(u);
                        }}
                      >
                        Сбросить пароль
                      </button>
                      <button
                        type="button"
                        className={`btn-row${u.is_active ? " btn-row-danger" : ""}`}
                        disabled={pendingId === u.id}
                        onClick={() => {
                          if (u.is_active) {
                            setDialogError(null);
                            setBlockUser(u);
                          } else {
                            void applyActive(u, true);
                          }
                        }}
                      >
                        {u.is_active ? "Заблокировать" : "Разблокировать"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {resetUser && (
          <ResetPasswordDialog
            user={resetUser}
            busy={pendingId === resetUser.id}
            error={dialogError}
            onClose={() => setResetUser(null)}
            onConfirm={(pw) => void confirmReset(resetUser, pw)}
          />
        )}
        {blockUser && (
          <BlockDialog
            user={blockUser}
            busy={pendingId === blockUser.id}
            error={dialogError}
            onClose={() => setBlockUser(null)}
            onConfirm={() => void applyActive(blockUser, false)}
          />
        )}
      </div>
    </div>
  );
}
