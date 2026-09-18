// Витрина дизайн-токенов: собирает frontend/design-preview/*.html из
// tokens.css (источник правды) + шаблонов design-preview-src/.
// Использование: node scripts/build-design-preview.mjs
// env DESIGN_PREVIEW_OUT — переопределить выходную директорию (для тестов).
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = process.env.DESIGN_PREVIEW_OUT ?? join(ROOT, "design-preview");
const SRC = join(ROOT, "design-preview-src");

/** :root-блок tokens.css → { имя-без-префикса: значение } */
export function parseTokens(css) {
  const root = css.match(/:root\s*\{([\s\S]*?)\n\}/);
  if (!root) throw new Error("tokens.css: :root не найден");
  const tokens = {};
  for (const m of root[1].matchAll(/--([\w-]+):\s*([^;]+);/g)) tokens[m[1]] = m[2].trim();
  return tokens;
}

/** "var(--x)" → конечное значение (рекурсивно). */
export function resolveVar(tokens, value) {
  const m = /^var\(--([\w-]+)\)$/.exec(value);
  return m ? resolveVar(tokens, tokens[m[1]]) : value;
}

function fontFace(family, file, weight, format) {
  const data = readFileSync(join(ROOT, "public/fonts", file)).toString("base64");
  return `@font-face { font-family: "${family}"; font-weight: ${weight}; font-display: swap;
  src: url(data:font/${format};base64,${data}) format("${format}"); }`;
}

function page(group, title, body, tokensBlock, fonts) {
  return `<!-- @dsCard group="${group}" -->
<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>${title}</title>
<style>
${fonts}
:root {
${tokensBlock}
}
* { box-sizing: border-box; }
body { margin: 0; padding: 24px; background: var(--bg); color: var(--ink);
  font-family: var(--font-ui); font-size: 13px; }
h1 { font-family: var(--font-display); font-size: 20px; letter-spacing: -0.02em; margin: 0 0 16px; }
h2 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--muted); margin: 24px 0 8px; }
.grid { display: flex; flex-wrap: wrap; gap: 12px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: var(--r-card); padding: 16px; }
code { font-size: 11px; color: var(--muted); }
</style></head><body>
${body}
</body></html>
`;
}

function swatch(tokens, name) {
  const value = tokens[name];
  const color = resolveVar(tokens, value);
  return `<div class="card" style="padding:10px; width:132px">
  <div style="height:48px; border-radius: var(--r-row); border:1px solid var(--line); background:${color}"></div>
  <div style="margin-top:8px; font-weight:500">--${name}</div>
  <code>${value}</code>
</div>`;
}

function buildColorsBody(tokens) {
  const primitives = Object.keys(tokens).filter((k) => /^(gray|red|blue|green)-\d/.test(k));
  const aliases = ["bg", "card", "ink", "muted", "line", "hover", "active", "accent", "accent-hover", "dark", "user-bubble"]
    .filter((k) => k in tokens);
  return `<h1>Цвет</h1>
<h2>Примитивы Kurs</h2>
<div class="grid">${primitives.map((n) => swatch(tokens, n)).join("\n")}</div>
<h2>Семантические алиасы</h2>
<div class="grid">${aliases.map((n) => swatch(tokens, n)).join("\n")}</div>`;
}

const tokensCss = readFileSync(join(ROOT, "src/styles/tokens.css"), "utf8");
const tokens = parseTokens(tokensCss);
const tokensBlock = Object.entries(tokens).map(([k, v]) => `  --${k}: ${v};`).join("\n");
const fonts = [
  fontFace("Alfa Interface Sans", "alfa-interface-sans_regular.woff2", 400, "woff2"),
  fontFace("Alfa Interface Sans", "alfa-interface-sans_medium.woff2", 500, "woff2"),
  fontFace("Alfa Interface Sans", "alfa-interface-sans_bold.woff2", 700, "woff2"),
  fontFace("Styrene A LC Black", "Styrene-A-LC-Black.woff", "400 900", "woff"),
].join("\n");

const pages = [
  ["colors", "Colors", "Цвет — токены Нейроюриста", buildColorsBody(tokens)],
  ["type", "Type", "Типографика — Нейроюрист", readFileSync(join(SRC, "type.html"), "utf8")],
  ["geometry", "Geometry", "Геометрия — Нейроюрист", readFileSync(join(SRC, "geometry.html"), "utf8")],
  // components.ssr.html — генерат scripts/render-components.tsx (SSR настоящих
  // core-components); design:preview запускает его перед этим скриптом.
  ["components", "Components", "Компоненты — Нейроюрист", readFileSync(join(SRC, "components.ssr.html"), "utf8")],
];

mkdirSync(OUT, { recursive: true });
for (const [file, group, title, body] of pages) {
  const html = page(group, title, body, tokensBlock, fonts);
  writeFileSync(join(OUT, `${file}.html`), html);
  console.log(`design-preview: ${file}.html (${Math.round(html.length / 1024)} KiB)`);
}
