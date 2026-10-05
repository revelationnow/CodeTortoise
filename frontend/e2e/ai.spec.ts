import { expect, test } from "@playwright/test";
import { contrast, login, startReview } from "./helpers";

const AI = "http://127.0.0.1:8798";      // e2e/serve-ai.sh: CodeTortoise with the fake model in e2e/fake_llm.py

test.describe("with an AI", () => {
  test.use({ baseURL: AI });

  test("✦ Explain rewrites a flow that the up-front pass left", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}?view=graph&flow=2`);
    const what = page.getByRole("region", { name: "Flow" }).locator(".ws-flow-text p").first();
    const ask = what.getByRole("button", { name: /Explain/ });
    await expect(ask).toHaveText("✦ Explain");
    await expect(ask).toHaveAttribute("title", /^1 AI call · \d+ left on this review$/);
    await expect(what).not.toContainText("reaches logger_flush, which drops it");
    await ask.click();
    await expect(what).toContainText("The new -2 from uart_send reaches logger_flush, which drops it.", { timeout: 30_000 });
    await expect(what.locator(".ai-label")).toBeVisible();
    await expect(ask).toHaveText("✦ Explain again");
  });

  test("✦ Explain retells a story's title and summary, on the story and in the rail", async ({ page }) => {
    await startReview(page);
    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
    const head = page.locator(".ws-story-head");
    await expect(head.locator(".ai-label")).toHaveCount(0);                  // this server's up-front pass skips stories
    await head.getByRole("button", { name: "✦ Explain" }).click();
    await expect(head.locator("h2")).toContainText("uart_send's new error count reaches uart_errors", { timeout: 30_000 });
    await expect(head.locator(".ai-label")).toBeVisible();
    await expect(head.getByRole("button", { name: /Explain/ })).toHaveText("✦ Explain again");
    await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }))
      .toContainText("uart_send's new error count reaches uart_errors");
  });

  test("✦ Explain on a story with its graph open neither flashes Loading nor redraws the graph", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/s/S1?view=graph`);
    await expect(page.locator(".ws-graph .bd-node").first()).toBeVisible();
    await page.getByRole("button", { name: "Whole graph" }).click();
    await page.evaluate(() => {
      const w = window as unknown as { loading: number };
      w.loading = 0;
      (document.querySelector(".ws-graph") as HTMLElement).dataset.kept = "yes";     // gone if the graph remounts
      new MutationObserver(() => { if (document.querySelector("main")?.textContent?.includes("Loading S")) w.loading++; })
        .observe(document.body, { subtree: true, childList: true, characterData: true });
    });
    const head = page.locator(".ws-story-head");
    await head.getByRole("button", { name: "✦ Explain" }).click();
    await expect(head.locator("h2")).toContainText("uart_send's new error count reaches uart_errors", { timeout: 30_000 });
    await expect(page.locator(".ws-graph .bd-node").first()).toBeVisible();
    expect(await page.evaluate(() => (window as unknown as { loading: number }).loading)).toBe(0);
    await expect(page.locator(".ws-graph")).toHaveAttribute("data-kept", "yes");
    await expect(page.getByRole("button", { name: "Whole graph" })).toHaveAttribute("aria-pressed", "true");
  });

  test("a story shows the flow narrative the up-front pass wrote, and ✦ Explain on another flow updates it", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    const board = await (await page.request.get(`/api/reviews/${rid}/board`)).json();
    const ss = await (await page.request.get(`/api/reviews/${rid}/stories`)).json();
    const told = board.flows.find((f: { what_source: string }) => f.what_source === "llm");
    const sid = ss.flow_story[told.id];
    const s = ss.stories.find((x: { id: string }) => x.id === sid);
    await page.goto(`${base}/s/${sid}?flow=${s.flows.indexOf(told.id) + 1}`);
    const what = page.getByRole("region", { name: "Flow" }).locator(".ws-flow-text p").first();
    await expect(what.locator(".ai-label")).toBeVisible();                     // the board's narrative, on the story
    await expect(what.getByRole("button", { name: /Explain/ })).toHaveText("✦ Explain again");
    const other = ss.stories.flatMap((x: { id: string; flows: string[] }) => x.flows.map((f) => [x.id, f]))
      .find(([, f]: string[]) => f !== told.id)!;
    const st = ss.stories.find((x: { id: string }) => x.id === other[0]);
    await page.goto(`${base}/s/${other[0]}?flow=${st.flows.indexOf(other[1]) + 1}`);
    const ask = what.getByRole("button", { name: /Explain/ });
    await expect(ask).toHaveText("✦ Explain");
    await ask.click();
    await expect(what).toContainText("The new -2 from uart_send reaches logger_flush, which drops it.", { timeout: 30_000 });
    await expect(ask).toHaveText("✦ Explain again");
  });

  test("a high finding's page shows the analysis the up-front pass wrote, without asking", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    const findings: { id: string; severity: string }[] = await (await page.request.get(`/api/reviews/${rid}/findings`)).json();
    const high = findings.find((f) => f.severity === "high")!;
    expect(high, "the fixture has a high finding").toBeTruthy();
    await page.goto(`${base}/f/${high.id}`);
    const ai = page.getByRole("region", { name: "AI analysis" });
    await expect(ai).toContainText("uart_send can now return -2, and logger_flush drops it.", { timeout: 30_000 });
    await expect(ai.locator(".ai-label")).toBeVisible();
    await expect(ai.getByRole("button", { name: /Explain again/ })).toBeVisible();
  });

  test("✦ Summarise sums up a file in its diff", async ({ page }) => {
    await startReview(page);
    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
    const panel = page.getByRole("complementary", { name: "Code: uart.c" });
    await panel.getByRole("button", { name: /Summarise/ }).click();
    await expect(panel).toContainText("This file now counts transmit errors.", { timeout: 30_000 });
    await expect(panel).toContainText("Check the readers of uart_errors.");
  });

  test("the owner raises the budget from the AI pill; a reviewer sees the usage without the control", async ({ page, browser }) => {
    await startReview(page);
    const pill = page.getByRole("button", { name: /^AI \d+\/200$/ });
    expect(await contrast(page, ".ws-head .ai-pill")).toBeGreaterThanOrEqual(4.5);   // readable on the light head
    await pill.click();
    const usage = page.getByRole("dialog", { name: "AI usage" });
    await expect(usage).toContainText("By purpose: finding 1 · flow 1 · summary 1");
    await usage.getByText(/^All calls/).click();                          // the call list loads when opened
    await expect(usage.locator(".ai-calls tbody tr")).toHaveCount(3);
    await usage.getByLabel("New budget").fill("300");
    await usage.getByRole("button", { name: "Raise budget" }).click();
    await expect(page.getByRole("button", { name: /^AI \d+\/300$/ })).toBeVisible();
    await expect(usage.getByLabel("Rounds per @tortoise answer")).toHaveValue("10");
    await usage.getByLabel("Rounds per @tortoise answer").fill("4");
    await usage.getByRole("button", { name: "Set rounds" }).click();
    await expect(usage).toContainText("One @tortoise answer is 1 AI call of up to 4 rounds.");

    const bob = await browser.newPage({ baseURL: AI });
    await login(bob, "bob");
    await bob.goto(page.url());
    await bob.getByRole("button", { name: /^AI \d+\/300$/ }).click();
    const theirs = bob.getByRole("dialog", { name: "AI usage" });
    await expect(theirs).toContainText("You today: 0 of 100");
    await expect(theirs.getByRole("button", { name: "Raise budget" })).toHaveCount(0);
    await expect(theirs).toContainText("One @tortoise answer is 1 AI call of up to 4 rounds.");
    await expect(theirs.getByRole("button", { name: "Set rounds" })).toHaveCount(0);
    await bob.close();
  });

  test("Health shows the AI limits and today's calls", async ({ page }) => {
    await login(page);
    await page.goto("/health");
    const card = page.locator(".card", { has: page.getByRole("heading", { name: "AI calls" }) });
    await expect(card).toContainText("Limits: 200 a review · 100 a person a day · 10 rounds for one @tortoise answer (1 call");
    await expect(card).toContainText(/Today: \d+ calls across reviews/);
  });
});
