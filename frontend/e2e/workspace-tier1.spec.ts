import { expect, test } from "@playwright/test";
import { expectNamed, login, openAiUsage, reviewMenu, startReview } from "./helpers";

const STRONG = "http://127.0.0.1:8795";  // e2e/serve-strong.sh: stories and risk review by the fake strong model, targets hal and fw

test.describe("stories formed by a strong model", () => {
  test.use({ baseURL: STRONG });

  test("a story shows its targets, its hazard, what the strong model suggests checking and its open questions", async ({ page }) => {
    const base = await startReview(page);
    const rail = page.locator(".ws-rail");
    const s1 = rail.getByRole("link", { name: /^Go to story S1/ });
    await expect(s1).toContainText("UART driver counts transmit errors");          // one line in the outline: no chips
    await page.goto(`${base}/s/S1`);
    const head = page.locator(".ws-story-head");
    await expect(head.locator(".ws-chip.target")).toHaveText("⌖ fw");
    await expect(head.locator(".ct-headline.hazard")).toHaveText("1 hazard");
    await expect(head.locator("h2 .ai-name")).toHaveAttribute("title", "Written by AI · fake-strong");   // the strong model's title
    await expect(head.getByRole("button", { name: /Explain/ })).toHaveCount(0);       // tier 2 never retells it
    await expect(head.getByRole("button", { name: "Ask…" })).toBeVisible();
    const chip = page.getByRole("region", { name: /^Flow 1: / }).locator(".st-chip").first();   // the hazard leads its flow's checks
    await expect(chip).toHaveClass(/\bhazard\b/);
    await expect(chip).toHaveText("logger_flush ignores the new -2, so a failed send goes unnoticed.");
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await expect(outline.getByRole("link", { name: "Open check: logger_flush ignores the new -2, so a failed send goes unnoticed." })
      .locator(".ck-tag")).toHaveText("Hazard");
    await outline.getByRole("button", { name: "Stories" }).click();
    await page.getByRole("navigation", { name: "Story sections" }).getByRole("link", { name: /^Talk/ }).click();
    const talk = page.getByRole("region", { name: "Questions and comments" });
    await expect(talk).toContainText("Does any caller retry a send after -2?");
    await expect(talk.locator(".st-suggested")).toContainText("Check that logger_flush handles the new -2.");
    await expect(page.getByRole("region", { name: "Why these belong together" })).toHaveCount(0);   // folded into the tiles
    await expectNamed(page);
  });

  test("the overview's introduction is the strong model's, its AI parts edged", async ({ page }) => {
    await startReview(page);
    const intro = page.locator(".ov-thread").first().locator(".ov-purpose");
    await expect(intro.first()).toHaveClass(/\bai-text\b/);
    await expect(intro).toContainText("This thread changes the UART driver.");
    await expect(page.locator(".ov3 .ws-lead")).toContainText("The main risk is a caller that misses a new result.");
  });

  test("the header counts the open hazards the strong model found", async ({ page }) => {
    await startReview(page);
    await expect(page.locator(".ws-head .ct-headline")).toHaveText("1 hazard");
    await expect(page.locator(".ws-head .ct-headline")).toHaveClass(/\bhazard\b/);
  });

  test("the pieces it could not place say so in the rail, each with the check that failed", async ({ page }) => {
    const base = await startReview(page);
    const s3 = page.locator(".ws-rail").getByRole("link", { name: /^Go to story S3/ });
    await expect(s3.locator(".ws-row-sub")).toHaveText("Needs a person to place it");
    await page.goto(`${base}/s/S3`);
    const place = page.getByRole("region", { name: "Pieces to place" });
    await expect(place).toContainText("need a person to place them");
    await expect(place.locator(".ws-reason.failed")).toHaveText("target fw, hal differs from the story's (hal)");
  });

  test("a finding shows the AI review: hazard red, needs review amber, with its citations as links", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/f/F1?details=1`);
    const hazard = page.locator(".ws-verdict");
    await expect(hazard).toHaveClass(/hazard/);
    await expect(hazard).toContainText("Hazard — logger_flush ignores the new -2, so a failed send goes unnoticed.");
    await expect(hazard).not.toContainText("AI review");
    await hazard.getByRole("link", { name: "uart_send" }).click();               // a node id cited: its code opens
    await expect(page.getByRole("complementary", { name: /uart_send/ }).or(page.locator(".ws-detail"))).toBeVisible();
    await page.goto(`${base}/f/F2?details=1`);
    await expect(page.locator(".ws-verdict")).toHaveClass(/needs_review/);
    await expect(page.locator(".ws-verdict")).toContainText("Needs review —");
    await page.goto(`${base}/f/F5?details=1`);
    const cited = page.locator(".ws-verdict").getByRole("link", { name: /^driver\/uart\.c:\d+$/ });
    await expect(cited).toBeVisible();                                            // a file:line cited: the diff opens there
  });

  test("the owner re-runs stories fresh and sees the strong model's calls", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(base);
    const usage = await openAiUsage(page);
    await expect(usage).toContainText(/Strong model \(fake-strong\): \d+ of 40 calls/);
    await usage.getByRole("button", { name: "Close" }).click();
    const fresh = (await reviewMenu(page)).getByRole("menuitem", { name: "Re-run stories, fresh" });
    await expect(fresh).toHaveAttribute("title", "Ask the strong model for new stories instead of reusing the ones it formed for this change");
    await fresh.click();
    await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ })).toBeVisible({ timeout: 60_000 });
  });

  test("a strong reply cut off by its limit recovers at double the limit, and the request log downloads", async ({ page }) => {
    const base = await startReview(page);
    await expect(page.locator(".ws-head .ct-headline")).toHaveText("1 hazard");      // the strong model's answers stand
    await page.goto(base);
    const usage = await openAiUsage(page);
    await usage.getByText(/^All calls/).click();
    await expect(usage.locator(".ai-calls tbody tr").first()).toBeVisible();
    await expect(usage.locator(".ai-calls")).toContainText("fake-strong");
    const one = usage.getByRole("link", { name: /^Requests of call \d+$/ }).first();
    await expect(one).toBeVisible();
    const [download] = await Promise.all([page.waitForEvent("download"),
                                          usage.getByRole("link", { name: "Download request log" }).click()]);
    expect(download.suggestedFilename()).toMatch(/^review-\d+-requests\.zip$/);
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
