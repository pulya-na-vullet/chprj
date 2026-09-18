import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { TemplateSummary } from "../api/types";
import { TemplatesView } from "../components/templates/TemplatesView";

const startTemplate = vi.fn();
vi.mock("../state/ChatContext", () => ({
  useChat: () => ({ startTemplate }),
}));

const jsonResponse = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as Response;

const template = (over: Partial<TemplateSummary>): TemplateSummary => ({
  slug: "arenda-kvartiry",
  title: "Договор аренды квартиры",
  category: "Договоры",
  description: "Наём жилого помещения между физлицами",
  field_count: 12,
  ...over,
});

afterEach(() => {
  vi.unstubAllGlobals();
  startTemplate.mockClear();
});

it("показывает скелетоны, затем категории и карточки", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      jsonResponse({
        templates: [
          template({}),
          template({ slug: "uslugi", title: "Договор оказания услуг", field_count: 10 }),
          template({
            slug: "raspiska",
            title: "Расписка о займе",
            category: "Личные документы",
            field_count: 7,
          }),
        ],
      }),
    ),
  );
  const { container } = render(<TemplatesView />);
  expect(container.querySelectorAll(".templates-skel").length).toBeGreaterThan(0);
  await waitFor(() => expect(screen.getByText("Договор аренды квартиры")).toBeInTheDocument());
  expect(container.querySelector(".templates-skel")).not.toBeInTheDocument();
  // категории в порядке сервера
  const cats = [...container.querySelectorAll(".templates-cat")].map((el) => el.textContent);
  expect(cats).toEqual(["Договоры", "Личные документы"]);
  // склонение счётчика полей
  expect(screen.getByText("12 полей")).toBeInTheDocument();
  expect(screen.getByText("7 полей")).toBeInTheDocument();
});

it("пустая витрина — «Шаблоны скоро появятся»", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse({ templates: [] })),
  );
  render(<TemplatesView />);
  await waitFor(() => expect(screen.getByText("Шаблоны скоро появятся")).toBeInTheDocument());
});

it("ошибка раздела — баннер и повторная загрузка по «Обновить»", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(jsonResponse({ detail: "boom" }, 503))
    .mockResolvedValueOnce(jsonResponse({ templates: [template({})] }));
  vi.stubGlobal("fetch", fetchMock);
  render(<TemplatesView />);
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "Обновить" }));
  await waitFor(() => expect(screen.getByText("Договор аренды квартиры")).toBeInTheDocument());
});

it("клик по карточке стартует заполнение выбранного шаблона", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse({ templates: [template({})] })),
  );
  render(<TemplatesView />);
  await waitFor(() => expect(screen.getByText("Договор аренды квартиры")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: /Договор аренды квартиры/ }));
  expect(startTemplate).toHaveBeenCalledWith("arenda-kvartiry", "Договор аренды квартиры");
});
