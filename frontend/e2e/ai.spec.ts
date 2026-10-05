import { expect, test } from "@playwright/test";
import { login, startReview, startStories } from "./helpers";

const AI = "http://127.0.0.1:8798";      // e2e/serve-ai.sh: CodeTortoise with the fake model in e2e/fake_llm.py

test.describe("with an AI", () => {
  test.use({ baseURL: AI });

  test("✦ Explain rewrites a flow that the up-front pass left", async ({ page }) => {
    await startReview(page);
    await page.getByRole("tablist", { name: "Call flows" }).getByRole("tab").nth(1).click();
    const info = page.locator(".bd-flowinfo");
    const ask = info.getByRole("button", { name: /Explain/ });
    await expect(ask).toHaveText("✦ Explain");
    await expect(ask).toHaveAttribute("title", /^1 AI call · \d+ left on this review$/);
    await expect(info.locator(".what")).not.toContainText("reaches logger_flush, which drops it");
    await ask.click();
    await expect(info.locator(".what")).toContainText("The new -2 from uart_send reaches logger_flush, which drops it.",
                                                      { timeout: 30_000 });
    await expect(info.locator(".what .ai-label")).toBeVisible();
    await expect(ask).toHaveText("✦ Explain again");
  });

  test("✦ Explain retells a story's title and summary, on the story and in the list", async ({ page }) => {
    await startStories(page);
    await page.locator(".st-entry").first().click();
    const head = page.locator(".st-head");
    await expect(head.locator(".ai-label")).toHaveCount(0);                  // this server's up-front pass skips stories
    await head.getByRole("button", { name: "✦ Explain" }).click();
    await expect(head.locator("h2")).toContainText("uart_send's new error count reaches uart_errors", { timeout: 30_000 });
    await expect(head.locator(".ai-label")).toBeVisible();
    await expect(head.getByRole("button", { name: /Explain/ })).toHaveText("✦ Explain again");
    await page.getByRole("link", { name: "Stories", exact: true }).first().click();
    await expect(page.locator(".st-entry").first()).toContainText("uart_send's new error count reaches uart_errors");
  });

  test("a story shows the flow narrative the up-front pass wrote, and ✦ Explain on another flow updates it", async ({ page }) => {
    await startStories(page);
    const rid = page.url().match(/\/r\/(\d+)/)![1];
    const board = await (await page.request.get(`/api/reviews/${rid}/board`)).json();
    const ss = await (await page.request.get(`/api/reviews/${rid}/stories`)).json();
    const told = board.flows.find((f: { what_source: string }) => f.what_source === "llm");
    const sid = ss.flow_story[told.id];
    const s = ss.stories.find((x: { id: string }) => x.id === sid);
    await page.goto(`/r/${rid}/s/${sid}`);
    const what = page.locator(".ph-what");
    for (let i = 0; i < s.flows.indexOf(told.id); i++) await page.getByRole("button", { name: "Next flow" }).click();
    await expect(what.locator(".ai-label")).toBeVisible();                     // the board's narrative, on the story
    await expect(what.getByRole("button", { name: /Explain/ })).toHaveText("✦ Explain again");
    const other = ss.stories.flatMap((x: { id: string; flows: string[] }) => x.flows.map((f) => [x.id, f]))
      .find(([, f]: string[]) => f !== told.id)!;
    await page.goto(`/r/${rid}/s/${other[0]}`);
    const st = ss.stories.find((x: { id: string }) => x.id === other[0]);
    for (let i = 0; i < st.flows.indexOf(other[1]); i++) await page.getByRole("button", { name: "Next flow" }).click();
    const ask = what.getByRole("button", { name: /Explain/ });
    await expect(ask).toHaveText("✦ Explain");
    await ask.click();
    await expect(what).toContainText("The new -2 from uart_send reaches logger_flush, which drops it.", { timeout: 30_000 });
    await expect(ask).toHaveText("✦ Explain again");
  });

  test("the owner raises the budget from the AI pill; a reviewer sees the usage without the control", async ({ page, browser }) => {
    await startReview(page);
    const pill = page.getByRole("button", { name: /^AI \d+\/200$/ });
    await pill.click();
    const usage = page.getByRole("dialog", { name: "AI usage" });
    await expect(usage).toContainText("By purpose: finding 1 · flow 1 · summary 1");
    await usage.getByText(/^All calls/).click();                          // the call list loads when opened
    await expect(usage.locator(".ai-calls tbody tr")).toHaveCount(3);
    await usage.getByLabel("New budget").fill("300");
    await usage.getByRole("button", { name: "Raise budget" }).click();
    await expect(page.getByRole("button", { name: /^AI \d+\/300$/ })).toBeVisible();

    const bob = await browser.newPage({ baseURL: AI });
    await login(bob, "bob");
    await bob.goto(page.url());
    await bob.getByRole("button", { name: /^AI \d+\/300$/ }).click();
    const theirs = bob.getByRole("dialog", { name: "AI usage" });
    await expect(theirs).toContainText("You today: 0 of 100");
    await expect(theirs.getByRole("button", { name: "Raise budget" })).toHaveCount(0);
    await bob.close();
  });

  test("Health shows the AI limits and today's calls", async ({ page }) => {
    await login(page);
    await page.goto("/health");
    const card = page.locator(".card", { has: page.getByRole("heading", { name: "AI calls" }) });
    await expect(card).toContainText("Limits: 200 a review · 100 a person a day · 6 for one @tortoise answer");
    await expect(card).toContainText(/Today: \d+ calls across reviews/);
  });
});
