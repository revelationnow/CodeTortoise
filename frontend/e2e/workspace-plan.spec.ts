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

  test("progress shows in the header, the outline and the overview; the last story read leads to the overview", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const { order } = await readingOf(page, base);
    const head = page.locator(".ws-head .ws-progress");
    const line = (k: number) => new RegExp(`^${k} of ${order.length} stories read( · (\\d+ causes? open|every check done))?$`);
    await expect(head).toHaveText(line(0));
    for (const sid of order.slice(0, -1))
      expect((await page.request.put(`/api${base.replace("/r/", "/reviews/")}/ticks/story/${sid}`)).ok()).toBe(true);
    await page.goto(`${base}/s/${order.at(-1)}`);
    await expect(head).toHaveText(line(order.length - 1));
    const rail = page.locator(".ws-rail");
    await expect(rail.locator(".ws-read", { hasText: "✓" })).toHaveCount(order.length - 1);
    await expect(rail.getByRole("link", { name: new RegExp(`^Go to story ${order[0]}: .* \\(read\\)`) })).toBeVisible();
    await expect(rail.locator(".ws-thread .ws-thread-read").first()).toHaveText(/^, \d+ of \d+ read$/);
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await expect(page.getByText("You've read every story.")).toBeVisible();
    await expect(head).toHaveText(line(order.length));
    const metas = page.locator(".ov-thread .ov-meta");
    for (const m of await metas.allInnerTexts()) expect(m).toMatch(/^(\d+) stor(y|ies) · \1 read( · |$)/);
  });

  test("a failed load of the reader's ticks says so and keeps the reading plan (review M5)", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const { order } = await readingOf(page, base);
    await page.goto(`${base}/s/${order[0]}`);
    await expect(page.getByRole("button", { name: "Mark as read" })).toBeVisible();
    await page.route("**/ticks", (r) => (r.request().method() === "GET" ? r.fulfill({ status: 500, json: { detail: "ticks are down" } })
      : r.continue()));
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page.locator(".st-read .banner")).toHaveText("ticks are down");
    await expect(page).toHaveURL(new RegExp(`${base}/s/${order[0]}$`));
    await expect(page.getByRole("button", { name: "Mark as read" })).toBeVisible();
    await expect(page.locator(".ws-head .ws-progress")).toBeVisible();
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
    await expect(page.locator(".ws-rail .ws-read", { hasText: "✓" })).toHaveCount(0);
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

  test("stepping onto a place ticks it read for that reader alone; Looks fine marks it for everyone", async ({ page, browser }) => {
    const base = await startReview(page, FOUR);
    const id = base.split("/")[2];
    await page.getByRole("link", { name: "Next open check" }).click();
    const key = await (async () => {
      const r = await (await page.request.get(`/api/reviews/${id}/reading`)).json() as { causes: { kind: string; places: string[] }[] };
      return r.causes.filter((c) => c.kind !== "confirm")[0].places[0];
    })();
    await expect.poll(async () => (await (await page.request.get(`/api/reviews/${id}/ticks`)).json()).checks).toContain(key);
    const other = await browser.newPage();
    await login(other, "bob");
    expect((await (await other.request.get(`/api/reviews/${id}/ticks`)).json()).checks).not.toContain(key);
    await page.getByRole("button", { name: "Looks fine & next" }).click();
    await expect.poll(async () => Object.keys((await (await other.request.get(`/api/reviews/${id}/reading`)).json()).marks)).toContain(key);
    await other.close();
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the overview's threads carry the progress the header leaves out, and Mark as read fits", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const { order } = await readingOf(page, base);
    await page.goto(`${base}/s/${order[0]}`);
    await expect(page.locator(".ws-head .ws-progress")).toBeHidden();
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/${order[1]}$`));
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await page.goto(base);
    await page.getByRole("link", { name: "Go to the overview" }).click();
    await expect(page.locator(".ov-thread .ov-meta").filter({ hasText: " · 1 read" })).toHaveCount(1);   // its thread counts it
  });
});
