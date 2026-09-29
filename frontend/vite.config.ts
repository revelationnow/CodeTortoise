/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../backend/codetortoise/web/static", emptyOutDir: true, chunkSizeWarningLimit: 3000 },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
