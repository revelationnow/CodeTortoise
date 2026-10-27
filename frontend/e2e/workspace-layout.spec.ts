import { expect, type Locator, type Page, test } from "@playwright/test";
import { SCROLLERS, startReview, storyLink } from "./helpers";

/** Layout (owner feedback 2026-10-08, sub-project C): a wider story page with a divider, code in the side panel, a
 * resizable review header; the overview and the text pages as wide (owner feedback 2026-10-09). */

test.use({ viewport: { width: 1440, height: 900 } });

async function drag(page: Page, grip: Locator, dx: number, dy: number) {
  const b = (await grip.boundingBox())!;
  const x = b.x + b.width / 2, y = b.y + b.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, { steps: 6 });
  await page.mouse.up();
}
const width = (l: Locator) => l.evaluate((el) => el.getBoundingClientRect().width);
const height = (l: Locator) => l.evaluate((el) => el.getBoundingClientRect().height);

async function story(page: Page) {
  const base = await startReview(page);
  await (await storyLink(page, /^Go to story S1/)).click();
  await expect(page.locator(".ws-story-head h2")).toContainText("uart_send can now return -2");
  return base;
}

test("a function's code opens in the side panel from the story's Code, leaving the inline code as it was", async ({ page }) => {
  const base = await story(page);
  await page.getByRole("navigation", { name: "Story sections" }).getByRole("link", { name: /^Code/ }).click();
  const code = page.getByRole("region", { name: "Code" });
  const row = code.locator("details.st-fn", { hasText: "uart_send" });
  await row.getByRole("link", { name: "Open uart_send in the side panel" }).click();
  await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`${base}/s/S1\\?open=`));
  await expect(row).not.toHaveAttribute("open", "");                          // the row stayed shut
  await row.locator("summary").click();
  await expect(row.locator(".bd-code").first()).toBeVisible();
  await row.getByRole("link", { name: "Open uart_send in the side panel" }).click();
  await expect(row).toHaveAttribute("open", "");                              // and stays open
});

test("the scrollers the sideways check reads each exist once on a story page with a panel open", async ({ page }) => {
  const base = await story(page);
  await page.goto(`${base}/s/S1?open=${encodeURIComponent("file://fixture/driver/uart.c")}`);
  await expect(page.getByRole("complementary", { name: "Code: uart.c" })).toBeVisible();
  for (const scroller of SCROLLERS) await expect(page.locator(scroller), `${scroller}, which sideways() reads`).toHaveCount(1);
});

test("the review header can be dragged taller or down to one line, scrolls what no longer fits, and double-click restores it", async ({ page }) => {
  await story(page);
  const box = page.locator(".ws-headbox"), head = page.locator(".ws-head");
  const natural = await height(box);
  await drag(page, box.locator("> .bd-resizer"), 0, 200);
  await expect.poll(() => height(box)).toBeGreaterThan(natural + 150);
  const tall = await height(box);
  await page.reload();
  await expect.poll(() => height(page.locator(".ws-headbox"))).toBe(tall);
  await drag(page, box.locator("> .bd-resizer"), 0, -400);
  await expect.poll(() => height(box)).toBe(40);
  expect(await head.evaluate((el) => getComputedStyle(el).overflowY)).toBe("auto");
  await box.locator("> .bd-resizer").dblclick();
  await expect.poll(() => height(box)).toBe(natural);
});

test("the stepper's actions wrap inside the side panel at its narrowest", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.addInitScript(() => window.localStorage.setItem("ct.ws.detailW", "320"));
  await startReview(page);
  const outline = page.locator("aside.ws-outline");
  await outline.getByRole("button", { name: "Checks" }).click();
  await outline.locator(".ws-row.cause", { has: page.locator(".ck-tag.reader") }).first().click();   // the longest row: + its sink mark
  const panel = page.locator(".ws-detail"), acts = panel.locator(".cs-acts");
  const mark = acts.getByRole("button", { name: "Treat Uart::errors as a sink" });
  await expect(mark).toBeVisible();
  expect(await acts.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
  const right = (l: Locator) => l.evaluate((el) => el.getBoundingClientRect().right);
  expect(await right(mark)).toBeLessThanOrEqual(await right(panel));
});

test("the overview and a story fill the centre", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1000 });                  // a centre wider than the old 1280px cap
  await startReview(page);
  const centre = page.getByRole("region", { name: "Centre" });
  expect(await width(page.locator(".ws-page > .ov3"))).toBeGreaterThan(Math.min(900, (await width(centre)) - 80));
  await expect(page.locator(".ov2-check")).toHaveCount(0);
  await (await storyLink(page, /^Go to story S1/)).click();
  await expect(page.locator(".ws-story-head h2")).toContainText("uart_send can now return -2");
  expect(await width(page.locator(".ws-page > .st-page"))).toBeGreaterThan((await width(centre)) - 80);   // only the page padding
});

test("a CL page and a finding page fill the centre", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1000 });
  const base = await startReview(page);
  const centre = page.getByRole("region", { name: "Centre" });
  for (const path of ["/cl/101", "/f/F4?details=1"]) {
    await page.goto(base + path);
    const text = page.locator(".ws-page > .ws-text");
    await expect(text.locator("h2").first()).toBeVisible();
    expect(await width(text), path).toBeGreaterThan((await width(centre)) - 80);   // no 880px cap
  }
});
