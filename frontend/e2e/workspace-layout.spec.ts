import { expect, type Locator, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

/** Layout (owner feedback 2026-10-08, sub-project C): a wider story page with a divider, code in the side panel, a
 * resizable review header. */

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
  await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
  await expect(page.locator(".ws-story-head h2")).toContainText("uart_send can now return -2");
  return base;
}

test("the story fills the centre and a divider sets the To check column's width, kept after a reload", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1000 });                  // a centre wider than the old 1280px cap
  await story(page);
  const tiles = page.locator(".st-tiles"), check = page.getByRole("complementary", { name: "What to check in this story" });
  const centre = page.getByRole("region", { name: "Centre" });
  expect(await width(tiles)).toBeGreaterThan((await width(centre)) - 80);     // no 1280px cap: only the page padding
  const before = await width(check);
  await drag(page, page.locator(".st-check > .bd-resizer"), -120, 0);
  await expect.poll(() => width(check)).toBeGreaterThan(before + 100);
  const after = await width(check);
  await page.reload();
  await expect.poll(() => width(page.getByRole("complementary", { name: "What to check in this story" }))).toBe(after);
  await page.locator(".st-check > .bd-resizer").dblclick();
  await expect.poll(() => width(check)).toBe(before);
});

test("a function's code opens in the side panel from the story's Code, leaving the inline code as it was", async ({ page }) => {
  const base = await story(page);
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

test("a check row's actions wrap inside the To check column at its narrowest", async ({ page }) => {
  await story(page);
  const check = page.getByRole("complementary", { name: "What to check in this story" });
  const mark = check.getByRole("button", { name: "Treat Uart::errors as a sink" });
  await expect(mark).toBeVisible();
  const right = (l: Locator) => l.evaluate((el) => el.getBoundingClientRect().right);
  expect(await right(mark)).toBeLessThanOrEqual(await right(check));
});
