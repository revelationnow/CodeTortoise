import { devices, expect, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

/** CLs as a sequence (spec 2026-10-07-review-reading-phase2): fixture CL 103 adds logger_init's `lg->level = 1;`,
 * CL 104 adds logger_level, CL 105 rewrites CL 103's line to `lg->level = 2;`. */
const STACK = "103 104 105";

async function openLogger(page: Page, base: string) {
  await page.goto(`${base}/i/files`);
  await page.getByRole("link", { name: "Open logger.c's diff" }).click();
  return page.getByRole("complementary", { name: "Code: logger.c" });
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the combined diff chips each run of rows with the CL that wrote it, and a chip shows that CL alone", async ({ page }) => {
    const code = await openLogger(page, await startReview(page, STACK));
    await expect(code.locator(".cl-chip .long")).toHaveText(["CL 105 · rewrites CL 103", "CL 104"]);
    await code.getByRole("button", { name: "CL 104: show CL 104 alone" }).click();
    await expect(code.getByLabel("Changelist")).toHaveValue("104");
    await expect(code.locator(".cl-chip")).toHaveCount(0);
  });

  test("an earlier CL's own diff greys the lines a later CL rewrote and says which", async ({ page }) => {
    const code = await openLogger(page, await startReview(page, STACK));
    await code.getByLabel("Changelist").selectOption("103");
    const row = code.locator(".bd-ln.rw");
    await expect(row).toHaveCount(1);
    await expect(row).toContainText("lg->level = 1;");
    await expect(row.locator(".cl-chip .long")).toHaveText("rewritten in CL 105");
    await row.getByRole("button", { name: /show CL 105 alone/ }).click();
    await expect(code.getByLabel("Changelist")).toHaveValue("105");
  });

  test("a story's Where groups its files by CL in reading order, says the order, and names the rewrite", async ({ page }) => {
    await startReview(page, STACK);
    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S\d+: .*logger_init/ }).click();
    const where = page.getByRole("region", { name: "Where" });
    await expect(where.locator(".st-order")).toHaveText("Read CL 103, then CL 105");
    await expect(where.locator(".st-clgroup h4")).toHaveText(["CL 103 · 1 file"]);
    await expect(where.getByRole("group", { name: "CL 103" }).locator(".st-file .ws-chip")).toHaveText("also CL 105");
    await expect(where.locator(".st-rewrites li")).toHaveText("CL 105 rewrites 1 line CL 103 added in logger_init");
    await where.getByRole("link", { name: "Open logger_init at line 7, in all CLs" }).click();
    const code = page.getByRole("complementary", { name: "Code: logger.c" });
    await expect(code.getByLabel("Changelist")).toHaveValue("all");
    await expect(code.locator(".bd-ln.focus")).toContainText("lg->level = 2;");
  });

  test("a CL page names its rewrites both ways, and a CL outside the review between two of its CLs", async ({ page }) => {
    let base = await startReview(page, STACK);
    await page.goto(`${base}/cl/105`);
    const rw = page.getByRole("region", { name: "Rewrites" });
    await expect(rw.locator("li")).toHaveText("rewrites lines CL 103 added: logger_init (1 line)");
    await page.goto(`${base}/cl/103`);
    await expect(rw.locator("li")).toHaveText("lines it added are rewritten by CL 105: logger_init (1 line)");
    await rw.getByRole("link", { name: "Open logger_init at line 7, in all CLs" }).click();
    const code = page.getByRole("complementary", { name: "Code: logger.c" });
    await expect(code.getByLabel("Changelist")).toHaveValue("all");                      // not CL 103's own diff
    await expect(code.locator(".bd-ln.focus")).toContainText("lg->level = 2;");
    await page.goto(`${base}/cl/104`);
    await expect(page.getByRole("heading", { name: "Stories drawn from this CL" })).toBeVisible();
    await expect(rw).toHaveCount(0);
    base = await startReview(page, "103 105");
    await page.goto(`${base}/cl/105`);
    await expect(rw.locator("li")).toHaveText([
      "rewrites lines CL 103 added: logger_init (1 line)",
      "logger.c: a CL outside this review changed it between CL 103 and CL 105"]);
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("chips shrink to the CL number", async ({ page }) => {
    const code = await openLogger(page, await startReview(page, STACK));
    await expect(code.locator(".cl-chip .short")).toHaveText(["105", "104"]);
    await expect(code.locator(".cl-chip .long").first()).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
