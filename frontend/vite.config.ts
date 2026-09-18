/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const API_ROUTES = [
  "/auth",
  "/profile",
  "/chat",
  "/conversations",
  "/acts",
  "/sources",
  "/library",
  "/documents",
  "/playbooks",
  "/reviews",
  "/templates",
  "/healthz",
];
const proxy = Object.fromEntries(
  API_ROUTES.map((p) => [p, { target: "http://127.0.0.1:8000", changeOrigin: true }]),
);

// Экосистема разметки ответа (react-markdown и весь micromark/mdast/hast под
// ним) — один кусок: она нужна только там, где рендерится текст ответа.
const MARKDOWN_PACKAGES =
  /[\\/]node_modules[\\/](react-markdown|remark-.*|rehype-.*|micromark.*|mdast-.*|hast-.*|unist-.*|vfile.*|property-information|space-separated-tokens|comma-separated-tokens|character-entities.*|decode-named-character-reference|html-url-attributes|trim-lines|zwitch|longest-streak|ccount|escape-string-regexp|markdown-table|devlop|bail|is-plain-obj|trough|extend|unified)[\\/]/;

export default defineConfig({
  plugins: [react()],
  server: { proxy },
  build: {
    outDir: "../src/neurolegal/agent/api/static",
    emptyOutDir: true,
    // JS делится на куски, стили — нет: один app.css со стабильным именем
    // (иначе на каждый вендор-кусок появляется свой файл, и имена «уплывают»).
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        // Библиотеки — отдельными кусками (T-0143): они меняются редко, и
        // релиз продукта больше не сбрасывает их из кэша браузера вместе с
        // нашим кодом. Разделы приложения уезжают в свои куски через
        // React.lazy в App.tsx.
        manualChunks: (id: string) => {
          if (!id.includes("node_modules")) return undefined;
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) {
            return "vendor-react";
          }
          if (id.includes("@alfalab")) return "vendor-alfa";
          if (MARKDOWN_PACKAGES.test(id)) return "vendor-markdown";
          return "vendor";
        },
        entryFileNames: "app.js",
        chunkFileNames: "app-[name].js",
        assetFileNames: (info) =>
          info.name && info.name.endsWith(".css") ? "app.css" : "assets/[name][extname]",
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
