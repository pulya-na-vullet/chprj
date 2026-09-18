import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";

// NB: the relative path is kept in a variable rather than inlined as a string
// literal in `new URL(...)` — Vite statically detects the literal-argument
// form of `new URL("<literal>", import.meta.url)` as an asset-URL reference
// and rewrites it to a dev-server-relative URL, which breaks path resolution
// under vitest. A variable argument isn't pattern-matched, so it resolves to
// a real file:// URL as expected.
const scriptRelPath = "../../scripts/build-design-preview.mjs";
const script = new URL(scriptRelPath, import.meta.url).pathname;
const ssrRelPath = "../../scripts/render-components.tsx";
const ssrScript = new URL(ssrRelPath, import.meta.url).pathname;
const frontendRelPath = "../..";
const frontendDir = new URL(frontendRelPath, import.meta.url).pathname;

it("собирает витрину из tokens.css", () => {
  const out = mkdtempSync(join(tmpdir(), "design-preview-"));
  // сначала SSR-фрагмент компонентов (components.ssr.html), затем сборка страниц
  execFileSync("npx", ["vite-node", ssrScript], { cwd: frontendDir });
  execFileSync("node", [script], { env: { ...process.env, DESIGN_PREVIEW_OUT: out } });

  const colors = readFileSync(join(out, "colors.html"), "utf8");
  // первая строка — маркер карточки DesignSync
  expect(colors.split("\n")[0]).toBe('<!-- @dsCard group="Colors" -->');
  // живое значение из tokens.css, а не копипаста
  expect(colors).toContain("#EF3124");
  expect(colors).toContain("--red-01");
  expect(colors.length).toBeLessThan(256 * 1024); // лимит DesignSync на файл

  for (const page of ["type", "geometry", "components"]) {
    const html = readFileSync(join(out, `${page}.html`), "utf8");
    expect(html.split("\n")[0]).toMatch(/^<!-- @dsCard group="/);
    expect(html).toContain(":root {");
    expect(html.length).toBeLessThan(256 * 1024); // лимит DesignSync на файл
  }

  // components — настоящий SSR core-components: реальные классы пакетов
  const components = readFileSync(join(out, "components.html"), "utf8");
  expect(components).toContain("button__component");
  expect(components).toContain("checkbox__box");
});
