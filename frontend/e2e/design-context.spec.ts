import { devices, expect } from "@playwright/test";
import { login, reviewMenu, sideways, startReview, STRONG, test } from "./helpers";

// e2e/serve-strong.sh's fake strong model (e2e/fake_llm.py) says in its verdict when the prompt carries a design context.
const NOTES = "The UART must never drop a byte: a write that is too long is refused whole, and its sender is told.";

async function openPanel(page: import("@playwright/test").Page) {
  await (await reviewMenu(page)).getByRole("menuitem", { name: "Design context…" }).click();
  const panel = page.getByRole("dialog", { name: "Design context" });
  await expect(panel).toBeVisible();
  return panel;
}

test.describe("the design context", () => {
  test.use({ baseURL: STRONG, viewport: { width: 1440, height: 900 } });

  test("the owner gives the review a design context; the design stage runs again and the opening says it read it", async ({ page }) => {
    await startReview(page);
    const verdict = page.locator(".ov-top .dz-verdict");
    await expect(verdict.locator(".dz-src")).toHaveText("AI, from the stories");
    const panel = await openPanel(page);
    await panel.getByLabel("Notes").fill(NOTES);
    await expect(panel.locator(".dc-count")).toHaveText(`${NOTES.length} of 12,000 characters`);
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(panel.getByRole("status")).toContainText("Saved");
    await expect(verdict.locator(".dz-src")).toHaveText("AI, from the stories and the design context", { timeout: 30_000 });
    await expect(verdict.locator("p.ai-text")).toContainText("against its design context");
    await expect(page.getByRole("region", { name: "What it must get right" }).locator(".dz-src"))
      .toHaveText("AI, from the stories and the design context");
  });

  test("a condition added by hand leads the condition fold, and one the code lacks is said in the panel", async ({ page }) => {
    await startReview(page);
    const panel = await openPanel(page);
    await panel.getByLabel("Condition, as the code writes it").fill("reg == REG_CTRL");
    await panel.getByLabel("In the function (optional)").fill("hal_write");
    await panel.getByRole("button", { name: "Add the condition" }).click();
    await panel.getByLabel("Condition, as the code writes it").fill("x == 1");
    await panel.getByRole("button", { name: "Add the condition" }).click();
    await expect(panel.locator(".dc-added li")).toHaveCount(2);
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("heading", { name: /Writes to any other register · \d+ changes? still runs?$/ }))
      .toBeVisible({ timeout: 30_000 });   // its name starts "Written by AI: ", the AI mark
    await expect(panel.locator(".dc-notes li")).toHaveText(["The condition x == 1 is not in the changed functions."]);
  });

  test("someone else in the review reads the design context but has nothing to change it with", async ({ page, browser }) => {
    const base = await startReview(page);
    const panel = await openPanel(page);
    await panel.getByLabel("Notes").fill(NOTES);
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(panel.getByRole("status")).toContainText("Saved");
    const context = await browser.newContext({ baseURL: STRONG });
    const other = await context.newPage();
    await login(other, "bob");
    await other.goto(base);
    const theirs = await openPanel(other);
    await expect(theirs.locator(".dc-read")).toContainText(NOTES);
    await expect(theirs.getByRole("textbox")).toHaveCount(0);
    await expect(theirs.getByRole("button", { name: "Save" })).toHaveCount(0);
    await context.close();
  });

  test("a review started with a design context opens with the opening that read it", async ({ page }) => {
    await login(page);
    await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
    await page.getByLabel("Design context (optional)").fill(NOTES);
    await page.getByRole("button", { name: "Start review" }).click();
    await expect(page.locator(".ov-top .dz-verdict .dz-src")).toHaveText("AI, from the stories and the design context",
                                                                          { timeout: 60_000 });
  });
});

test.describe("the design context on a phone", () => {
  test.use({ baseURL: STRONG, viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
             deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the panel fits the phone's width and nothing scrolls sideways", async ({ page }) => {
    await startReview(page);
    const panel = await openPanel(page);
    await panel.getByLabel("Notes").fill(NOTES);
    const box = await panel.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(devices["iPhone 13"].viewport.width);
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });
});
