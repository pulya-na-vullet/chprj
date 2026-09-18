import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { TemplatesTab } from "../../admin/components/TemplatesTab";
import type { AdminTemplateOut, TemplateField } from "../../admin/types";

const jsonResponse = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response;

const field = (name: string, over: Partial<TemplateField> = {}): TemplateField => ({
  name,
  label: name,
  hint: null,
  kind: "text",
  required: true,
  ...over,
});

const template = (over: Partial<AdminTemplateOut> = {}): AdminTemplateOut => ({
  slug: "arenda-kvartiry",
  title: "Аренда квартиры",
  category: "Договоры",
  description: "Договор аренды",
  status: "draft",
  fields: [field("landlord_fio"), field("rent", { kind: "money" })],
  created_at: "2026-08-13T00:00:00Z",
  updated_at: "2026-08-13T00:00:00Z",
  ...over,
});

afterEach(() => vi.unstubAllGlobals());

it("показывает скелетон, затем таблицу со статусами", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse({ templates: [template()] })),
  );
  const { container } = render(<TemplatesTab />);
  expect(container.querySelector(".users-skel")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText("Аренда квартиры")).toBeInTheDocument());
  expect(screen.getByText("Черновик")).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
});

it("пустая витрина — подсказка про первый шаблон", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse({ templates: [] })),
  );
  render(<TemplatesTab />);
  await waitFor(() => expect(screen.getByText(/Шаблонов пока нет/)).toBeInTheDocument());
});

it("загрузка .docx создаёт шаблон: slug генерируется из названия, POST с FormData", async () => {
  const created = template({ slug: "novyi-shablon", title: "Новый шаблон" });
  let uploadedForm: FormData | null = null;
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      uploadedForm = init.body as FormData;
      return jsonResponse(created, 201);
    }
    // до создания список пуст, после — с новым шаблоном
    return jsonResponse({ templates: uploadedForm ? [created] : [] });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<TemplatesTab />);
  await waitFor(() => expect(screen.getByText(/Шаблонов пока нет/)).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "Добавить шаблон" }));
  // поля slug в форме больше нет — оператор его не видит
  expect(screen.queryByLabelText("slug")).not.toBeInTheDocument();
  const file = new File(["docx-bytes"], "novy.docx");
  fireEvent.change(screen.getByTestId("template-file-input"), { target: { files: [file] } });
  fireEvent.change(screen.getByLabelText("Название"), { target: { value: "Новый шаблон" } });
  fireEvent.click(screen.getByRole("button", { name: "Создать" }));

  await waitFor(() => expect(screen.getByText(/создан черновиком/)).toBeInTheDocument());
  expect(uploadedForm).not.toBeNull();
  expect(uploadedForm!.get("slug")).toBe("novyi-shablon");
  expect(uploadedForm!.get("category")).toBe("Договоры");
  expect(uploadedForm!.get("file")).toBe(file);
  // шаблон появился в списке (и открылась его карточка — текст может дублироваться)
  await waitFor(() => expect(screen.getAllByText("Новый шаблон").length).toBeGreaterThan(0));
});

it("коллизия slug разрешается автосуффиксом: после 409 уходит повтор с -2", async () => {
  const slugs: string[] = [];
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      const form = init.body as FormData;
      slugs.push(String(form.get("slug")));
      if (slugs.length === 1) return jsonResponse({ detail: "template_exists" }, 409);
      return jsonResponse(template({ slug: String(form.get("slug")), title: "Аренда" }), 201);
    }
    return jsonResponse({ templates: [] });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<TemplatesTab />);
  await waitFor(() => expect(screen.getByText(/Шаблонов пока нет/)).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "Добавить шаблон" }));
  const file = new File(["docx-bytes"], "arenda.docx");
  fireEvent.change(screen.getByTestId("template-file-input"), { target: { files: [file] } });
  fireEvent.change(screen.getByLabelText("Название"), { target: { value: "Аренда" } });
  fireEvent.click(screen.getByRole("button", { name: "Создать" }));

  await waitFor(() => expect(screen.getByText(/создан черновиком/)).toBeInTheDocument());
  expect(slugs).toEqual(["arenda", "arenda-2"]);
});

it("исчерпание автосуффикса: пять 409 подряд — человеческая ошибка, без цикла", async () => {
  const slugs: string[] = [];
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") {
      slugs.push(String((init.body as FormData).get("slug")));
      return jsonResponse({ detail: "template_exists" }, 409);
    }
    return jsonResponse({ templates: [] });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<TemplatesTab />);
  await waitFor(() => expect(screen.getByText(/Шаблонов пока нет/)).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "Добавить шаблон" }));
  const file = new File(["docx-bytes"], "arenda.docx");
  fireEvent.change(screen.getByTestId("template-file-input"), { target: { files: [file] } });
  fireEvent.change(screen.getByLabelText("Название"), { target: { value: "Аренда" } });
  fireEvent.click(screen.getByRole("button", { name: "Создать" }));

  await waitFor(() =>
    expect(screen.getByText(/уже есть — измените название/)).toBeInTheDocument(),
  );
  expect(slugs).toEqual(["arenda", "arenda-2", "arenda-3", "arenda-4", "arenda-5"]);
});

it("карточка: пустая новая категория не уходит на сервер", async () => {
  const patchCalls: unknown[] = [];
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "PATCH") {
      patchCalls.push(JSON.parse(String(init.body)));
      return jsonResponse(template());
    }
    return jsonResponse({ templates: [template()] });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<TemplatesTab />);
  await waitFor(() => expect(screen.getByText("Аренда квартиры")).toBeInTheDocument());

  fireEvent.click(screen.getByText("Аренда квартиры"));
  fireEvent.change(await screen.findByLabelText("Категория"), {
    target: { value: "__new__" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(await screen.findByText("Категория не может быть пустой.")).toBeInTheDocument();
  expect(patchCalls).toEqual([]);
});

it("категория: пресеты в селекте, новая — только через явный пункт", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse({ templates: [] })),
  );
  render(<TemplatesTab />);
  await waitFor(() => expect(screen.getByText(/Шаблонов пока нет/)).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: "Добавить шаблон" }));
  const select = screen.getByLabelText("Категория");
  const labels = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
  expect(labels).toContain("Договоры");
  expect(labels).toContain("+ Новая категория…");

  fireEvent.change(select, { target: { value: "__new__" } });
  const input = screen.getByPlaceholderText("Название категории");
  fireEvent.change(input, { target: { value: "Иски" } });
  expect((input as HTMLInputElement).value).toBe("Иски");
  // возврат к списку восстанавливает выбор из существующих
  fireEvent.click(screen.getByRole("button", { name: "К списку" }));
  expect((screen.getByLabelText("Категория") as HTMLSelectElement).value).toBe("Договоры");
});

it("подпись, совпадающая с техническим именем, помечена в карточке", async () => {
  const t = template({
    fields: [field("landlord_fio"), field("rent", { label: "Арендная плата", kind: "money" })],
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse({ templates: [t] })),
  );
  render(<TemplatesTab />);
  await waitFor(() => expect(screen.getByText("Аренда квартиры")).toBeInTheDocument());

  fireEvent.click(screen.getByText("Аренда квартиры"));
  expect(await screen.findAllByText("подпись не задана")).toHaveLength(1);
});

it("публикация из карточки шлёт PATCH со status=published", async () => {
  const draft = template();
  const patchCalls: unknown[] = [];
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "PATCH") {
      patchCalls.push(JSON.parse(String(init.body)));
      return jsonResponse({ ...draft, status: "published" });
    }
    return jsonResponse({ templates: [draft] });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<TemplatesTab />);
  await waitFor(() => expect(screen.getByText("Аренда квартиры")).toBeInTheDocument());

  fireEvent.click(screen.getByText("Аренда квартиры"));
  fireEvent.click(await screen.findByRole("button", { name: "Опубликовать" }));

  await waitFor(() => expect(screen.getByText("Шаблон опубликован.")).toBeInTheDocument());
  expect(patchCalls).toEqual([{ status: "published" }]);
  expect(screen.getByText("Опубликован")).toBeInTheDocument();
});

it("замена файла показывает осиротевшие поля и даёт их убрать", async () => {
  const current = template();
  const afterReplace = {
    template: template({ fields: [field("landlord_fio"), field("rent"), field("tenant_fio")] }),
    added: ["tenant_fio"],
    orphaned: ["rent"],
  };
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "PUT") return jsonResponse(afterReplace);
    return jsonResponse({ templates: [current] });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<TemplatesTab />);
  await waitFor(() => expect(screen.getByText("Аренда квартиры")).toBeInTheDocument());

  fireEvent.click(screen.getByText("Аренда квартиры"));
  const file = new File(["v2"], "v2.docx");
  fireEvent.change(await screen.findByTestId("replace-file-input"), {
    target: { files: [file] },
  });

  await waitFor(() => expect(screen.getByText(/Файл заменён/)).toBeInTheDocument());
  expect(screen.getByText("нет в файле")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Убрать" }));
  expect(screen.queryByText("нет в файле")).not.toBeInTheDocument();
});

it("удаление — через подтверждение, DELETE уходит после «Удалить» в диалоге", async () => {
  const deleteCalls: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "DELETE") {
      deleteCalls.push(String(input));
      return { ok: true, status: 204, json: async () => ({}) } as Response;
    }
    return jsonResponse({ templates: deleteCalls.length ? [] : [template()] });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<TemplatesTab />);
  await waitFor(() => expect(screen.getByText("Аренда квартиры")).toBeInTheDocument());

  fireEvent.click(screen.getByText("Аренда квартиры"));
  fireEvent.click(await screen.findByRole("button", { name: "Удалить" }));
  expect(deleteCalls).toEqual([]);
  const dialogConfirm = screen
    .getAllByRole("button", { name: "Удалить" })
    .find((b) => b.className.includes("btn-primary"))!;
  fireEvent.click(dialogConfirm);

  await waitFor(() => expect(screen.getByText(/удалён/)).toBeInTheDocument());
  expect(deleteCalls).toEqual(["/admin/templates/arenda-kvartiry"]);
});
