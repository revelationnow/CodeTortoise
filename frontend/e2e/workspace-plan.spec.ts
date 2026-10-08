import { expect, type Page, test } from "@playwright/test";
import { login, startReview } from "./helpers";

/** The reading plan (spec 2026-10-07-review-reading-phase2 §6): each reader's own ticks on stories and checks. */
const FOUR = "101 102 103 104";

async function readingOf(page: Page, base: string): Promise<{ order: string[]; checks: { key: string }[] }> {
  return (await page.request.get(`/api${base.replace("/r/", "/reviews/")}/reading`)).json();
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("Mark as read ticks the story and goes to the next unread one; a read story offers Mark unread", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const { order } = await readingOf(page, base);
    await page.goto(`${base}/s/${order[1]}`);
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/${order[2]}$`));
    await page.goto(`${base}/s/${order[0]}`);
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/${order[2]}$`));      // order[1] is read already
    await page.goto(`${base}/s/${order[1]}`);
    await expect(page.locator(".st-read")).toHaveText("✓ Read · Mark unread");
    await page.getByRole("button", { name: "Mark unread" }).click();
    await expect(page.getByRole("button", { name: "Mark as read" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Mark as read" })).toBeVisible();
  });

  test("a check's Read box is the reader's own; Looks fine ticks it for the one who says it", async ({ page, browser }) => {
    const base = await startReview(page, FOUR);
    await page.getByRole("link", { name: "Go to the overview" }).click();
    const rows = page.locator(".ck-tile .ck-row");
    const [a, b] = [await rows.nth(0).getAttribute("data-key"), await rows.nth(1).getAttribute("data-key")];
    const row = (p: Page, key: string | null) => p.locator(`.ck-tile .ck-row[data-key="${key}"]`);
    await row(page, a).getByRole("checkbox", { name: "Read" }).click();          // checked once the server has it
    await expect(row(page, a).getByRole("checkbox", { name: "Read" })).toBeChecked();
    await expect(row(page, a)).toHaveClass(/\bread\b/);
    await row(page, b).getByRole("button", { name: "Looks fine" }).click();
    await expect(row(page, b).getByRole("checkbox", { name: "Read" })).toBeChecked();
    await page.reload();
    await expect(row(page, a).getByRole("checkbox", { name: "Read" })).toBeChecked();

    const other = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
    await login(other, "ana");
    await other.goto(`${base}`);
    await other.getByRole("link", { name: "Go to the overview" }).click();
    await expect(row(other, b).getByRole("button", { name: "Reopen" })).toBeVisible();     // the mark is shared…
    await expect(other.locator(".ck-tile").getByRole("checkbox", { name: "Read", checked: true })).toHaveCount(0);   // …the ticks are not
    await other.context().close();
  });
});
