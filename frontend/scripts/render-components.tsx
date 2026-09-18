// SSR-слепок настоящих core-components для витрины токенов.
// Запуск: vite-node scripts/render-components.tsx (см. npm run design:preview).
// Пишет design-preview-src/components.ssr.html (генерат, гитигнорен):
// маркап = renderToStaticMarkup наших обёрток src/ui/, стили = ровно те
// css-файлы пакетов, которые компоненты запросили через require('*.css'),
// плюс tree-shake переменных из @alfalab/core-components-vars.
import Module from "node:module";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

// ── 1. Перехват require('*.css'): CJS-пакеты core-components тянут свои
// стили обычным require; записываем порядок — это и есть точный набор CSS.
const cssFiles: string[] = [];
(Module as unknown as { _extensions: Record<string, (m: unknown, f: string) => void> })._extensions[
  ".css"
] = (_m, filename) => {
  if (!cssFiles.includes(filename)) cssFiles.push(filename);
};

// Импорты компонентов — только после установки хука (динамически).
const { renderToStaticMarkup } = await import("react-dom/server");
const React = await import("react");
const { Button } = await import("../src/ui/Button");
const { IconButton } = await import("../src/ui/IconButton");
const { Checkbox } = await import("../src/ui/Checkbox");
const { Skeleton } = await import("../src/ui/Skeleton");
const { Search } = await import("lucide-react");

const h = React.createElement;
const render = (node: React.ReactElement) => renderToStaticMarkup(node);

// ── 2. Маркап витрины (та же сетка, что и остальные страницы).
const buttons = [
  render(h(Button, { view: "primary", size: 40 }, "Новый чат")),
  render(h(Button, { size: 40 }, "Outlined (дефолт)")),
  render(h(Button, { view: "secondary", size: 40 }, "Secondary")),
  render(h(Button, { size: 40, disabled: true }, "Disabled")),
].join("\n  ");

const iconButton = render(h(IconButton, { icon: h(Search, { size: 16 }) }));

const checkboxes = [
  render(h(Checkbox, { label: "выбран", checked: true, onChange: () => {} })),
  render(h(Checkbox, { label: "не выбран", checked: false, onChange: () => {} })),
].join("\n  ");

const skeleton = render(
  h(Skeleton, { visible: true }, h("div", { style: { width: 180, height: 14 } })),
);

const body = `<h1>Компоненты (core-components, SSR)</h1>
<p><code>Маркап отрендерен renderToStaticMarkup из обёрток frontend/src/ui/*.tsx;
стили — настоящий CSS пакетов @alfalab/core-components-*.</code></p>
<h2>Button — view="outlined" size=40 по умолчанию; primary только для главного действия</h2>
<div class="grid" style="align-items:center">
  ${buttons}
</div>
<h2>IconButton — view="secondary" size=32</h2>
<div class="grid" style="align-items:center">
  ${iconButton}
</div>
<h2>Checkbox — size=20</h2>
<div class="grid" style="align-items:center; gap:20px">
  ${checkboxes}
</div>
<h2>Skeleton</h2>
<div class="grid">
  ${skeleton}
</div>
<h2>Tooltip / Popover — портальные, статические слепки</h2>
<div class="grid" style="align-items:flex-start">
  <span style="background: var(--gray-17); color: var(--gray-01); padding:6px 10px; border-radius: var(--r-row); font-size:12px">Подсказка — gray-17</span>
  <div class="card" style="width:220px; box-shadow: 0 4px 16px rgba(20,20,30,0.08)">Popover: карточка --r-card, тень низкая</div>
</div>
<p><code>Tooltip/Popover/Modal рендерятся порталами — в статике показаны слепки;
поведение см. frontend/src/ui/*.tsx.</code></p>`;

// ── 3. CSS: собранные файлы пакетов + :root-оверрайды core-theme.css.
// Витрина — desktop / светлая тема: inverted- и mobile-варианты не включаем.
const componentCss = cssFiles
  .filter((f) => !/inverted|\.mobile\./.test(f))
  .map((f) => readFileSync(f, "utf8"))
  .join("\n");
const coreTheme = readFileSync(join(ROOT, "src/styles/core-theme.css"), "utf8")
  .split("\n")
  .filter((line) => !line.trimStart().startsWith("@import"))
  .join("\n");

// ── 4. Tree-shake переменных: из core-components-vars берём только те
// --vars, на которые (транзитивно) ссылается собранный CSS. Полный
// colors-bluetint.css — 80 KiB, целиком не влезает в лимит DesignSync.
const VARS_DIR = join(ROOT, "node_modules/@alfalab/core-components-vars");
const VARS_FILES = [
  "colors-bluetint.css",
  "colors-addons.css",
  "shadows-bluetint.css",
  "border-radius.css",
  "gaps.css",
  "typography-vars.css",
  "common.css",
];

const varDefs = new Map<string, string>();
for (const file of VARS_FILES) {
  const css = readFileSync(join(VARS_DIR, file), "utf8");
  for (const m of css.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    if (!varDefs.has(m[1])) varDefs.set(m[1], m[2].trim());
  }
}

function collectVarRefs(text: string): Set<string> {
  const out = new Set<string>();
  for (const m of text.matchAll(/var\(\s*(--[\w-]+)/g)) out.add(m[1]);
  return out;
}

const needed = new Set<string>();
const queue = [...collectVarRefs(componentCss + coreTheme + body)];
while (queue.length) {
  const name = queue.shift()!;
  if (needed.has(name) || !varDefs.has(name)) continue;
  needed.add(name);
  queue.push(...collectVarRefs(varDefs.get(name)!));
}
const varsCss = `:root {\n${[...needed].map((n) => `  ${n}: ${varDefs.get(n)};`).join("\n")}\n}`;

// ── 5. Итоговый фрагмент: <style> + маркап.
const fragment = `<!-- generated by scripts/render-components.tsx — do not edit -->
<style>
${varsCss}
${coreTheme}
${componentCss}
</style>
${body}
`;

const outDir = join(ROOT, "design-preview-src");
mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, "components.ssr.html"), fragment);
console.log(
  `components.ssr: ${cssFiles.length} css files, ${needed.size} vars, ${Math.round(fragment.length / 1024)} KiB`,
);
