import { expect, test } from "@playwright/test";
import { expectNamed, login, startReview } from "./helpers";

const STRONG = "http://127.0.0.1:8795";  // e2e/serve-strong.sh: stories and risk review by the fake strong model, targets hal and fw

test.describe("stories formed by a strong model", () => {
  test.use({ baseURL: STRONG });

  test("a story shows its targets, why its pieces belong together, what to check, questions and related stories", async ({ page }) => {
    const base = await startReview(page);
    const rail = page.locator(".ws-rail");
    const s1 = rail.getByRole("link", { name: /^Go to story S1/ });
    await expect(s1).toContainText("UART driver counts transmit errors");
    await expect(s1.locator(".ws-chip.target")).toHaveText("⌖ fw");                    // two targets: chips in the rail
    await page.goto(`${base}/s/S1`);
    const head = page.locator(".ws-story-head");
    await expect(head.locator(".ws-chip.target")).toHaveText("⌖ fw");
    await expect(head.getByRole("button", { name: /Explain/ })).toHaveCount(0);       // tier 2 never retells it
    await expect(head.getByRole("button", { name: "Ask…" })).toBeVisible();
    await expect(page.getByRole("region", { name: "What to check" })).toContainText("Check that logger_flush handles the new -2.");
    await expect(page.getByRole("region", { name: "Open questions" })).toContainText("Does any caller retry a send after -2?");
    const why = page.getByRole("region", { name: "Why these belong together" });
    await expect(why.locator("li")).toHaveCount(2);
    await expect(why.locator("li").first()).toContainText("starts the story");
    await expect(why.locator("li").nth(1)).toContainText("same feature");
    await expect(why.getByRole("link", { name: "Open //fixture/driver/uart.c" })).toBeVisible();
    const related = page.getByRole("region", { name: "Related" });
    await related.getByRole("link", { name: "see S2 · hal" }).click();
    await expect(page.locator(".ws-story-head h2")).toContainText("HAL writes take an unsigned register");
    await expectNamed(page);
  });

  test("the pieces it could not place are listed last, each with the check that failed", async ({ page }) => {
    const base = await startReview(page);
    const group = page.getByRole("region", { name: /^Stories/ }).locator(".ws-group").last();
    await expect(group.locator("h3")).toHaveText("Needs a person to place these");
    await page.goto(`${base}/s/S3`);
    const place = page.getByRole("region", { name: "Pieces to place" });
    await expect(place).toContainText("need a person to place them");
    await expect(place.locator(".ws-reason.failed")).toHaveText("target fw, hal differs from the story's (hal)");
  });

  test("a finding shows the AI review: hazard red, needs review amber, with its citations as links", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/f/F1`);
    const hazard = page.locator(".ws-verdict");
    await expect(hazard).toHaveClass(/hazard/);
    await expect(hazard).toContainText("AI review: hazard — logger_flush ignores the new -2, so a failed send goes unnoticed.");
    await hazard.getByRole("link", { name: "uart_send" }).click();               // a node id cited: its code opens
    await expect(page.getByRole("complementary", { name: /uart_send/ }).or(page.locator(".ws-detail"))).toBeVisible();
    await page.goto(`${base}/f/F2`);
    await expect(page.locator(".ws-verdict")).toHaveClass(/needs_review/);
    await expect(page.locator(".ws-verdict")).toContainText("AI review: needs review —");
    await page.goto(`${base}/f/F5`);
    const cited = page.locator(".ws-verdict").getByRole("link", { name: /^driver\/uart\.c:\d+$/ });
    await expect(cited).toBeVisible();                                            // a file:line cited: the diff opens there
  });

  test("the owner re-runs stories fresh and sees the strong model's calls", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(base);
    await page.getByRole("button", { name: /^AI \d+\/\d+$/ }).click();
    const usage = page.getByRole("dialog", { name: "AI usage" });
    await expect(usage).toContainText(/Strong model \(fake-strong\): \d+ of 40 calls/);
    await usage.getByRole("button", { name: "Close" }).click();
    await page.getByRole("button", { name: "Re-run stories (fresh)" }).click();
    await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ })).toBeVisible({ timeout: 60_000 });
  });

  test("Health says plainly when code goes to a model off the network", async ({ page }) => {
    await login(page);
    await page.route("**/api/health*", async (route) => {
      const real = await (await route.fetch()).json();
      real.checks = real.checks.map((c: { name: string; detail: string }) => c.name === "strong model endpoint"
        ? { ...c, detail: "https://models.example.com/v1 (big); code from reviewed changes is sent to models.example.com" } : c);
      await route.fulfill({ json: real });
    });
    await page.goto("/health");
    await expect(page.getByRole("note")).toContainText("Code from reviewed changes is sent to models.example.com");
  });
});
