import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { UsersTab } from "../../admin/components/UsersTab";
import type { AdminUserOut } from "../../admin/types";

const jsonResponse = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response;

const user = (over: Partial<AdminUserOut>): AdminUserOut => ({
  id: "u1",
  email: "a@example.com",
  is_active: true,
  created_at: "2026-06-01T00:00:00Z",
  conversation_count: 3,
  ...over,
});

/** The confirm button inside the open modal (row button + dialog button can
 * share a label — pick the primary one). */
const dialogButton = (name: string) =>
  screen.getAllByRole("button", { name }).find((b) => b.className.includes("btn-primary"))!;

afterEach(() => vi.unstubAllGlobals());

it("shows a loading skeleton, then the users table", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse({ users: [user({})] })),
  );
  const { container } = render(<UsersTab />);
  expect(container.querySelector(".users-skel")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText("a@example.com")).toBeInTheDocument());
  expect(container.querySelector(".users-skel")).not.toBeInTheDocument();
  expect(screen.getByText("Активен")).toBeInTheDocument();
  expect(screen.getByText("3")).toBeInTheDocument();
});

it("shows the empty state when there are no users", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse({ users: [] })),
  );
  render(<UsersTab />);
  await waitFor(() => expect(screen.getByText("Пользователей пока нет")).toBeInTheDocument());
});

it("surfaces a 502 as 'agent unavailable'", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse({ detail: "agent unavailable" }, 502)),
  );
  render(<UsersTab />);
  await waitFor(() =>
    expect(screen.getByText("Агент недоступен. Повторите позже.")).toBeInTheDocument(),
  );
});

it("blocks a user through a confirmation dialog, then shows the flip and a notice", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/admin/users" && (!init || init.method === undefined)) {
      return jsonResponse({ users: [user({ is_active: true })] });
    }
    if (url === "/admin/users/u1" && init?.method === "PATCH") {
      expect(JSON.parse(String(init.body))).toEqual({ is_active: false });
      return jsonResponse(user({ is_active: false }));
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<UsersTab />);
  await waitFor(() => expect(screen.getByText("Активен")).toBeInTheDocument());

  // row button opens the dialog — no request yet
  fireEvent.click(screen.getByRole("button", { name: "Заблокировать" }));
  // the confirm modal is an accessible dialog labelled by its heading
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByText("Заблокировать a@example.com?")).toBeInTheDocument();
  expect(dialog).toHaveAttribute("aria-modal", "true");
  expect(fetchMock).toHaveBeenCalledTimes(1);

  fireEvent.click(dialogButton("Заблокировать"));
  await waitFor(() => expect(screen.getByText("Заблокирован")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Разблокировать" })).toBeInTheDocument();
  expect(screen.getByText(/заблокирован\. Открытые сессии завершены/)).toBeInTheDocument();
  // dialog gone
  expect(screen.queryByText("Заблокировать a@example.com?")).not.toBeInTheDocument();
});

it("cancels the block dialog without a request", async () => {
  const fetchMock = vi.fn(async () => jsonResponse({ users: [user({})] }));
  vi.stubGlobal("fetch", fetchMock);

  render(<UsersTab />);
  await waitFor(() => expect(screen.getByText("Активен")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "Заблокировать" }));
  fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
  expect(screen.queryByText("Заблокировать a@example.com?")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1); // only the initial list
});

it("closes a dialog on Escape", async () => {
  const fetchMock = vi.fn(async () => jsonResponse({ users: [user({})] }));
  vi.stubGlobal("fetch", fetchMock);

  render(<UsersTab />);
  await waitFor(() => expect(screen.getByText("Активен")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "Заблокировать" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1); // only the initial list
});

it("unblocks a blocked user in one click", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/admin/users" && (!init || init.method === undefined)) {
      return jsonResponse({ users: [user({ is_active: false })] });
    }
    if (url === "/admin/users/u1" && init?.method === "PATCH") {
      expect(JSON.parse(String(init.body))).toEqual({ is_active: true });
      return jsonResponse(user({ is_active: true }));
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<UsersTab />);
  await waitFor(() => expect(screen.getByText("Заблокирован")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "Разблокировать" }));
  await waitFor(() => expect(screen.getByText("Активен")).toBeInTheDocument());
  expect(screen.getByText(/разблокирован/)).toBeInTheDocument();
});

it("resets a user's password through the dialog (T-0026, operator reset)", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/admin/users" && (!init || init.method === undefined)) {
      return jsonResponse({ users: [user({})] });
    }
    if (url === "/admin/users/u1" && init?.method === "PATCH") {
      expect(JSON.parse(String(init.body))).toEqual({ new_password: "operator-set-pw1" });
      return jsonResponse(user({}));
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<UsersTab />);
  await waitFor(() => expect(screen.getByText("a@example.com")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "Сбросить пароль" }));
  const input = screen.getByLabelText("Новый пароль");

  // client-side minimum mirrors the backend's 8-char rule
  fireEvent.change(input, { target: { value: "short12" } });
  fireEvent.click(dialogButton("Сохранить"));
  expect(await screen.findByText(/не короче 8 символов/)).toBeInTheDocument();

  fireEvent.change(input, { target: { value: "operator-set-pw1" } });
  fireEvent.click(dialogButton("Сохранить"));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/admin/users/u1",
      expect.objectContaining({ method: "PATCH" }),
    ),
  );
  // dialog closes on success and a confirmation notice appears
  await waitFor(() => expect(screen.queryByLabelText("Новый пароль")).not.toBeInTheDocument());
  expect(screen.getByText(/Пароль обновлён для a@example.com/)).toBeInTheDocument();
});

it("keeps the reset dialog open and shows the error when the request fails", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/admin/users" && (!init || init.method === undefined)) {
      return jsonResponse({ users: [user({})] });
    }
    return jsonResponse({ detail: "agent unavailable" }, 502);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<UsersTab />);
  await waitFor(() => expect(screen.getByText("a@example.com")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "Сбросить пароль" }));
  fireEvent.change(screen.getByLabelText("Новый пароль"), {
    target: { value: "operator-set-pw1" },
  });
  fireEvent.click(dialogButton("Сохранить"));

  // error is visible over the overlay, dialog stays open, button re-enabled
  await waitFor(() =>
    expect(screen.getByText("Агент недоступен. Повторите позже.")).toBeInTheDocument(),
  );
  const modal = screen.getByText("Агент недоступен. Повторите позже.").closest(".modal")!;
  expect(within(modal as HTMLElement).getByLabelText("Новый пароль")).toBeInTheDocument();
  expect(dialogButton("Сохранить")).not.toBeDisabled();
});

it("closes the reset dialog on cancel without a request", async () => {
  const fetchMock = vi.fn(async () => jsonResponse({ users: [user({})] }));
  vi.stubGlobal("fetch", fetchMock);

  render(<UsersTab />);
  await waitFor(() => expect(screen.getByText("a@example.com")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "Сбросить пароль" }));
  fireEvent.click(screen.getByRole("button", { name: "Отмена" }));
  expect(screen.queryByLabelText("Новый пароль")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1); // only the initial list
});
