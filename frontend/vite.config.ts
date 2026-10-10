/// <reference types="vitest/config" />
import { execSync } from "node:child_process";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

/** build.json beside the pages: the commit they were built from, which the Health page compares with the server's
 * (the built pages are not in git; a pull without a build keeps serving old ones). */
function buildStamp(): Plugin {
  return {
    name: "build-stamp",
    apply: "build",
    generateBundle() {
      let commit: string | null = null;
      try { commit = execSync("git rev-parse --short HEAD", { encoding: "utf8" }).trim() || null; } catch { /* not a checkout */ }
      this.emitFile({ type: "asset", fileName: "build.json", source: JSON.stringify({ commit }) });
    },
  };
}

export default defineConfig({
  plugins: [react(), buildStamp()],
  build: { outDir: "../backend/codetortoise/web/static", emptyOutDir: true, chunkSizeWarningLimit: 3000 },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
