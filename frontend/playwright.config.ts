import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:8799" },
  webServer: { command: "./e2e/serve.sh", url: "http://127.0.0.1:8799/api/me", timeout: 120_000, reuseExistingServer: false },
});
