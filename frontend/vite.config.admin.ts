import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const API_ROUTES = ["/admin", "/search", "/acts", "/healthz"];
const proxy = Object.fromEntries(
  API_ROUTES.map((p) => [p, { target: "http://127.0.0.1:8001", changeOrigin: true }]),
);

// Admin SPA: root=admin/ so the built entry is index.html (StaticFiles(html=True)
// serves it at /); bundle names are stable because the bundle is committed.
export default defineConfig({
  root: "admin",
  // Общий public/ с шрифтами бренда: дефолт admin/public не существует, и
  // собранная админка 404-ила на /fonts/*.woff2 (тихий откат на системные).
  publicDir: "../public",
  plugins: [react()],
  server: { proxy, port: 5174 },
  build: {
    outDir: "../../src/neurolegal/rag/api/static",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: "admin.js",
        chunkFileNames: "admin-[name].js",
        assetFileNames: (info) =>
          info.name && info.name.endsWith(".css") ? "admin.css" : "assets/[name][extname]",
      },
    },
  },
});
