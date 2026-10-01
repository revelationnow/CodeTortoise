import { devices, expect, test } from "@playwright/test";
import { startReview } from "./helpers";

test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
  deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

test("the board is usable at phone width", async ({ page }) => {
  await startReview(page);
  const { width, height } = page.viewportSize()!;
  const fits = async () => expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  await fits();

  // header controls are on screen
  const about = (await page.getByRole("button", { name: "✦ What's this change?" }).boundingBox())!;
  expect(about.x + about.width).toBeLessThanOrEqual(width);

  // a card is a bottom sheet
  await page.locator(".bd-flowinfo .step", { hasText: "uart_errors" }).click();
  const sheet = (await page.locator(".bd-card.sheet").boundingBox())!;
  expect(sheet.width).toBeGreaterThan(width - 24);
  expect(sheet.y + sheet.height).toBeGreaterThan(height - 16);

  // the viewer is a full-screen sheet
  await page.locator(".bd-card.sheet").getByRole("button", { name: "⤢ Full file" }).click();
  const viewer = (await page.locator(".bd-viewer").boundingBox())!;
  expect(Math.round(viewer.width)).toBe(width);
  await page.locator(".bd-viewer").getByRole("button", { name: "Close all" }).click();
  await expect(page.locator(".bd-viewer")).toHaveCount(0);

  // secondary tabs still work and diff line numbers never wrap digit by digit
  await page.getByRole("link", { name: /Files/ }).click();
  const ln = page.locator("tr.add td.ln").nth(1);
  expect((await ln.boundingBox())!.height).toBeLessThan(30);
  await fits();
});
