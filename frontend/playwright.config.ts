import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,                    // startReview alone may wait 60 s for analysis when every worker starts one
  use: { baseURL: "http://127.0.0.1:8799" },
  webServer: [
    { command: "./e2e/serve.sh", url: "http://127.0.0.1:8799/api/me", timeout: 120_000, reuseExistingServer: false },
    // AI tests (e2e/ai.spec.ts, e2e/mention.spec.ts): a fake OpenAI-compatible model and a CodeTortoise that uses it
    { command: "python3 e2e/fake_llm.py 8797", url: "http://127.0.0.1:8797/v1/models", timeout: 30_000, reuseExistingServer: false },
    { command: "bash e2e/serve-ai.sh", url: "http://127.0.0.1:8798/api/me", timeout: 120_000, reuseExistingServer: false },
    // large changes (the "a large change" tests in e2e/workspace*.spec.ts): the generated fixture whose CLs need several boards
    // two-tier stories (e2e/workspace-tier1.spec.ts): the fake model as the strong model too, the fixture split into targets
    { command: "bash e2e/serve-strong.sh", url: "http://127.0.0.1:8795/api/me", timeout: 120_000, reuseExistingServer: false },
    { command: "bash e2e/serve-large.sh", url: "http://127.0.0.1:8796/api/me", timeout: 120_000, reuseExistingServer: false },
  ],
});
