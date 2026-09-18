import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// Слой ui/ — единственное место в TS/TSX-коде, где разрешён импорт @alfalab/*.
// Тема (styles/core-theme.css) — единственное CSS-место.
const all = import.meta.glob<string>("../**/*.{ts,tsx}", {
  eager: true,
  query: "?raw",
  import: "default",
});

// T-0103: CSS читается через node:fs. `import.meta.glob(…, "?raw")` отдаёт для
// .css ПУСТЫЕ строки, поэтому CSS-гард ниже сканировал пустоту и был зелёным
// по построению — что бы в этих файлах ни лежало.
function readCss(): Record<string, string> {
  const srcDir = dirname(dirname(fileURLToPath(import.meta.url)));
  const out: Record<string, string> = {};
  const walk = (dir: string, prefix: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const abs = join(dir, entry.name);
      const rel = `${prefix}${entry.name}`;
      if (entry.isDirectory()) walk(abs, `${rel}/`);
      else if (entry.name.endsWith(".css")) out[rel] = readFileSync(abs, "utf8");
    }
  };
  walk(srcDir, "../");
  return out;
}

const allCss = readCss();

const isUi = (path: string) => path.startsWith("../ui/");
// T-0103: было `path.includes("/test/") || …` — любой ПРОДУКТОВЫЙ файл в
// каталоге с именем test оказывался невидим для гарда. Исключение только по
// имени самого файла.
const isTest = (path: string) => /\.test\.tsx?$/.test(path);
const isTheme = (path: string) => path === "../styles/core-theme.css";

describe("ui boundary", () => {
  it("не пускает @alfalab/* в продуктовый код мимо src/ui/", () => {
    for (const [path, src] of Object.entries(all)) {
      if (isUi(path) || isTest(path)) continue;
      expect(src, `${path} импортирует @alfalab напрямую — используй src/ui/`).not.toMatch(
        /@alfalab\//,
      );
    }
  });

  it("не пускает @alfalab/* в CSS мимо styles/core-theme.css", () => {
    for (const [path, src] of Object.entries(allCss)) {
      if (isTheme(path)) continue;
      expect(src, `${path} импортирует @alfalab напрямую — тема живёт в core-theme.css`).not.toMatch(
        /@alfalab\//,
      );
    }
  });

  it("src/ui/ существует и реэкспортирует core-components (санити скана)", () => {
    const uiFiles = Object.entries(all).filter(([p]) => isUi(p));
    expect(uiFiles.length, "src/ui/ ещё не создан").toBeGreaterThan(0);
    expect(uiFiles.some(([, src]) => /@alfalab\//.test(src))).toBe(true);
  });

  it("исключение — по имени файла, а не по каталогу", () => {
    // Было `path.includes("/test/")`: любой ПРОДУКТОВЫЙ файл, лежащий в
    // каталоге с именем test, выпадал из-под гарда целиком. Правило проверяется
    // на самом предикате: оно и есть та строка, которую легко ослабить обратно.
    expect(isTest("../components/test/Widget.tsx"), "продуктовый файл в каталоге test/").toBe(
      false,
    );
    expect(isTest("../components/testUtils.ts"), "не тест, просто имя похоже").toBe(false);
    expect(isTest("../test/Sidebar.test.tsx")).toBe(true);
    expect(isTest("../test/sse.test.ts")).toBe(true);
    expect(isTest("../components/Sidebar.tsx")).toBe(false);
  });

  it("CSS-скан действительно читает файлы (санити)", () => {
    // Без этой проверки гард по CSS зелен по построению: пустые строки не
    // матчатся ни на что. Ровно так он и работал до T-0103.
    expect(Object.keys(allCss).length).toBeGreaterThan(5);
    expect(allCss["../styles/core-theme.css"]).toMatch(/@alfalab\//);
    expect(Object.values(allCss).every((src) => src.length > 0)).toBe(true);
  });
});
