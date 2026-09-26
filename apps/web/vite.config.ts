import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// VITE_MOCK=1 serves every /api call from an in-browser mock built on docs/fixtures.
// The flag is compiled in as __MOCK__, so production builds contain no mock code or fixture data.
const mock = process.env.VITE_MOCK === "1";
const apiTarget = process.env.API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  base: "/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  define: {
    __MOCK__: JSON.stringify(mock),
  },
  server: {
    port: Number(process.env.PORT ?? 5173),
    strictPort: false,
    proxy: mock
      ? undefined
      : {
          "/api": { target: apiTarget, changeOrigin: false },
        },
  },
  preview: {
    port: 4173,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
  },
});
