import { expect, test } from "@playwright/test";
import { login, startReview } from "./helpers";

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

  test("the owner raises the budget from the AI pill; a reviewer sees the usage without the control", async ({ page, browser }) => {
    await startReview(page);
    const pill = page.getByRole("button", { name: /^AI \d+\/200$/ });
    await pill.click();
    const usage = page.getByRole("dialog", { name: "AI usage" });
    await expect(usage).toContainText("By purpose: flow 1 · summary 1");
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
