import { expect, it } from "vitest";
import { slugify } from "../../admin/util";

// Контракт сервера: TEMPLATE_SLUG_RE = ^[a-z0-9][a-z0-9-]{0,63}$
const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;

it("транслитерирует кириллицу в kebab-case", () => {
  expect(slugify("Аренда квартиры")).toBe("arenda-kvartiry");
  expect(slugify("Новый шаблон")).toBe("novyi-shablon");
  expect(slugify("Доверенность (общая)")).toBe("doverennost-obschaya");
});

it("съедает знаки и лишние дефисы, не роняя серверный формат", () => {
  for (const title of ["  Расписка о займе!  ", "Договор №5 — подряд", "ё, ъ и ь"]) {
    expect(slugify(title)).toMatch(SLUG_RE);
  }
  expect(slugify("Договор №5 — подряд")).toBe("dogovor-5-podryad");
});

it("пустое или несводимое название падает в заглушку", () => {
  expect(slugify("")).toBe("shablon");
  expect(slugify("«»…")).toBe("shablon");
});

it("длинное название обрезается до лимита slug (64)", () => {
  const long = "Очень ".repeat(30) + "длинное название";
  const slug = slugify(long);
  expect(slug.length).toBeLessThanOrEqual(64);
  expect(slug).toMatch(SLUG_RE);
});
