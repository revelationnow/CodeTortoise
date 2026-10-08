import { devices, expect, type Page, test } from "@playwright/test";
import { login, startReview } from "./helpers";

/** The reading plan (spec 2026-10-07-review-reading-phase2 §6): each reader's own ticks on stories and checks. */
const FOUR = "101 102 103 104";

async function readingOf(page: Page, base: string): Promise<{ order: string[]; checks: { key: string }[] }> {
  return (await page.request.get(`/api${base.replace("/r/", "/reviews/")}/reading`)).json();
}

/** Re-run the review and wait until the new run's reading is stored. */
async function rerun(page: Page, base: string) {
  const id = base.split("/")[2];
  const finished = async () => {
    const d = await (await page.request.get(`/api/reviews/${id}`)).json();
    return { status: d.review.status as string, at: d.stages.find((s: { name: string }) => s.name === "reading")?.finished_at as string };
  };
  const before = (await finished()).at;
  expect((await page.request.post(`/api/reviews/${id}/rerun`)).ok()).toBe(true);
  await expect.poll(async () => { const f = await finished(); return f.at !== before && ["done", "degraded"].includes(f.status); },
                    { timeout: 60_000 }).toBe(true);
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("progress shows in the header, the rail and the overview; the last story read leads to the overview", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const { order, checks } = await readingOf(page, base);
    const head = page.locator(".ws-head .ws-progress");
    await expect(head).toHaveText(`0 of ${order.length} stories read · 0 of ${checks.length} checks`);
    for (const sid of order.slice(0, -1))
      expect((await page.request.put(`/api${base.replace("/r/", "/reviews/")}/ticks/story/${sid}`)).ok()).toBe(true);
    await page.goto(`${base}/s/${order.at(-1)}`);
    await expect(head).toHaveText(`${order.length - 1} of ${order.length} stories read · 0 of ${checks.length} checks`);
    const rail = page.locator(".ws-rail");
    await expect(rail.locator(".ws-read")).toHaveCount(order.length - 1);
    await expect(rail.getByRole("link", { name: new RegExp(`^Go to story ${order[0]}: .* \\(read\\)$`) })).toBeVisible();
    await expect(rail.locator(".ws-thread .ws-thread-read").first()).toHaveText(/^\d+ of \d+$/);
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await expect(page.locator(".ov-progress")).toHaveText("You've read every story");
    await expect(head).toHaveText(`${order.length} of ${order.length} stories read · 0 of ${checks.length} checks`);
    await expect(page.locator(".ov-thread .ov-read").first()).toHaveText(/^(\d+) of \1 read$/);
  });

  test("a re-run clears every reader's ticks", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const { order } = await readingOf(page, base);
    await page.goto(`${base}/s/${order[0]}`);
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page.locator(".ws-head .ws-progress")).toContainText(`1 of ${order.length} stories read`);
    await rerun(page, base);
    await page.reload();
    await expect(page.locator(".ws-head .ws-progress")).toContainText(`0 of ${order.length} stories read`);
    await expect(page.locator(".ws-rail .ws-read")).toHaveCount(0);
  });

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

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the overview carries the progress the header leaves out, and Mark as read fits", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const { order } = await readingOf(page, base);
    await page.goto(`${base}/s/${order[0]}`);
    await expect(page.locator(".ws-head .ws-progress")).toBeHidden();
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/${order[1]}$`));
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await page.goto(base);
    await page.getByRole("link", { name: "Go to the overview" }).click();
    await expect(page.locator(".ov-progress")).toContainText(`1 of ${order.length} stories read`);
  });
});
