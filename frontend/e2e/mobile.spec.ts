import { devices, expect, test } from "@playwright/test";

test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
  deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

test("review pages are usable at phone width", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("P4 user").fill("demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.goto("/new");
  await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("heading", { name: "Summary" })).toBeVisible({ timeout: 45_000 });
  const width = page.viewportSize()!.width;

  // header: every nav control fits on screen
  const logout = await page.getByRole("button", { name: "Log out" }).boundingBox();
  expect(logout!.x + logout!.width).toBeLessThanOrEqual(width);

  // tabs: the last tab is reachable (scrolls into view) and fits once there
  const last = page.getByRole("link", { name: "CLs & Swarm" });
  await last.scrollIntoViewIfNeeded();
  const lb = await last.boundingBox();
  expect(lb!.x + lb!.width).toBeLessThanOrEqual(width);

  // diff: line numbers never wrap digit by digit
  await page.getByRole("link", { name: /Files/ }).click();
  const ln = page.locator("tr.add td.ln").nth(1);
  const box = await ln.boundingBox();
  expect(box!.height).toBeLessThan(30);

  // no page-level horizontal scrolling anywhere we looked
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
