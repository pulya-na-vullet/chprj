import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");

/** Примитивы Kurs из tokens.css: --gray/red/blue/green/yellow/beige-NN. */
function cssPrimitives(): Record<string, string> {
  const css = read("../styles/tokens.css");
  const root = /:root\s*\{([\s\S]*?)\n\}/.exec(css);
  if (!root) throw new Error("tokens.css: :root не найден");
  const out: Record<string, string> = {};
  for (const m of root[1].matchAll(/--((?:gray|red|blue|green|yellow|beige)-\d+):\s*([^;]+);/g)) {
    out[m[1]] = m[2].trim();
  }
  return out;
}

/** Блок colors: из YAML-frontmatter DESIGN.md (читает детектор impeccable). */
function frontmatterColors(): Record<string, string> {
  const md = read("../../../DESIGN.md");
  const fm = /^---\n([\s\S]*?)\n---/.exec(md);
  if (!fm) throw new Error("DESIGN.md: frontmatter не найден");
  const colors = /\ncolors:\n((?:[ ]{2}.+\n?)+)/.exec(fm[1]);
  if (!colors) throw new Error("DESIGN.md frontmatter: colors не найден");
  const out: Record<string, string> = {};
  for (const m of colors[1].matchAll(/^[ ]{2}([\w-]+):\s*"([^"]+)"/gm)) {
    out[m[1]] = m[2];
  }
  return out;
}

it("frontmatter DESIGN.md синхронен с примитивами tokens.css", () => {
  expect(frontmatterColors()).toEqual(cssPrimitives());
});

// ---------------------------------------------------------------------------
// T-0103, пункт 4. Выше сверяются два документа между собой — само правило
// «цвета только через токены» этим не проверяется никак: хардкод #ff00ff в
// styles/sidebar.css и инлайновый style={{color:"#123456"}} в TSX проходили
// молча. Ниже — реальный скан исходников.

/**
 * Файлы читаются через node:fs, а НЕ через `import.meta.glob(…, "?raw")`:
 * для .css Vite отдаёт по этому пути пустые строки (обнаружено здесь же —
 * из-за этого CSS-гард в uiBoundary.test.ts годами сканировал пустоту).
 */
function readTree(suffixes: string[]): Record<string, string> {
  // dirname дважды, а не `new URL("..", import.meta.url)`: под jsdom голый ".."
  // резолвится в http://localhost/... вместо file://.
  const srcDir = dirname(dirname(fileURLToPath(import.meta.url)));
  const out: Record<string, string> = {};
  const walk = (dir: string, prefix: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const abs = join(dir, entry.name);
      const rel = `${prefix}${entry.name}`;
      if (entry.isDirectory()) walk(abs, `${rel}/`);
      else if (suffixes.some((s) => entry.name.endsWith(s))) {
        out[rel] = readFileSync(abs, "utf8");
      }
    }
  };
  walk(srcDir, "../");
  return out;
}

const sources = readTree([".ts", ".tsx"]);
const stylesheets = readTree([".css"]);

/** Определения палитры: единственные два места, где литерал цвета законен. */
const PALETTE_FILES = new Set(["../styles/tokens.css", "../styles/core-theme.css"]);

/**
 * Палитры-данные вне UI-хрома (TS): генеративные аватар-пресеты (T-0127,
 * спека E19 §3.3) — цвета арта уходят в SVG data-URI и radial-градиенты,
 * куда var(--…) структурно не подставить (тот же случай, что %23-цвета в
 * data-URI admin/styles.css, см. комментарий к stripComments).
 */
const PALETTE_DATA_TS = new Set(["../util/avatarPreset.ts"]);

const isTestFile = (path: string) => /\.test\.tsx?$/.test(path);

/**
 * Комментарии — не стиль: в admin/styles.css номер палитры выписан рядом с
 * data-URI (в нём цвет закодирован как %23…, CSS-переменную туда не подставить).
 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

const COLOR_LITERAL =
  /#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b|\brgba?\(|\bhsla?\(/;

function offenders(files: Record<string, string>): string[] {
  const found: string[] = [];
  for (const [path, raw] of Object.entries(files)) {
    if (PALETTE_FILES.has(path) || PALETTE_DATA_TS.has(path) || isTestFile(path)) continue;
    stripComments(raw)
      .split("\n")
      .forEach((line, i) => {
        const hit = COLOR_LITERAL.exec(line);
        if (hit) found.push(`${path}:${i + 1}: ${hit[0]} — ${line.trim()}`);
      });
  }
  return found;
}

describe("цвета только через токены", () => {
  it("в CSS нет литералов цвета мимо tokens.css / core-theme.css", () => {
    expect(offenders(stylesheets), "используй var(--…) из tokens.css").toEqual([]);
  });

  it("в TS/TSX нет литералов цвета (в том числе в инлайновых стилях)", () => {
    expect(offenders(sources), "используй var(--…) из tokens.css").toEqual([]);
  });

  it("санити скана: он действительно читает исходники", () => {
    // Если glob перестанет что-либо находить, оба теста выше станут зелёными
    // по построению — эта проверка не даст такому пройти.
    const palette = Object.entries(stylesheets).filter(([p]) => PALETTE_FILES.has(p));
    expect(palette.length, "исключения из скана исчезли из дерева").toBe(PALETTE_FILES.size);
    // TS-исключение тоже обязано существовать и действительно быть палитрой —
    // иначе запись в allowlist протухла и её надо убрать.
    for (const p of PALETTE_DATA_TS) {
      expect(sources[p], `исключение ${p} исчезло из дерева`).toBeDefined();
      expect(COLOR_LITERAL.test(sources[p])).toBe(true);
    }
    // tokens.css — единственный источник литералов палитры; он обязан их иметь.
    expect(COLOR_LITERAL.test(stylesheets["../styles/tokens.css"])).toBe(true);
    expect(Object.keys(stylesheets).length).toBeGreaterThan(5);
    expect(Object.keys(sources).length).toBeGreaterThan(50);
  });
});
