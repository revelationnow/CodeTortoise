import { devices, expect, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
  deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

const tab = (page: Page, name: string) => page.locator(".ph-tabs").getByRole("tab", { name });

test("phone board: flow reader, files and summary tabs", async ({ page }) => {
  await startReview(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  await expect(page.locator(".topbar")).toBeHidden();                               // the review header is the only bar
  await expect(tab(page, "Flows")).toHaveAttribute("aria-selected", "true");

  // the first flow, as steps from entry to landing
  await expect(page.locator(".ph-title")).toHaveText("uart_errors sees a new writer of Uart::errors");
  await expect(page.locator(".ph-count")).toHaveText("1/3");
  const steps = page.locator(".ph-step");
  await expect(steps).toHaveCount(5);
  await expect(steps.nth(2)).toContainText("uart_send");
  await expect(steps.last()).toHaveClass(/\blanding\b/);
  await expect(page.locator(".ph-landing")).toContainText("Side effect lands on uart_errors");

  // swipe to the next flow, button back
  const box = (await page.locator(".ph-reader").boundingBox())!;
  await page.mouse.move(box.x + box.width - 30, box.y + 120);
  await page.mouse.down();
  await page.mouse.move(box.x + 40, box.y + 130, { steps: 6 });
  await page.mouse.up();
  await expect(page.locator(".ph-count")).toHaveText("2/3");
  await expect(page.locator(".ph-title")).toHaveText("logger_flush ignores -2");
  await page.getByRole("button", { name: "Previous flow" }).click();
  await expect(page.locator(".ph-count")).toHaveText("1/3");

  // a step expands to its code with annotations
  await steps.nth(2).locator(".ph-head").click();
  await expect(page.locator(".ph-step.open .bd-ann").first()).toContainText("writes Uart::errors through alias");

  // ⤢ opens the whole file in the Files tab at the function
  await page.locator(".ph-step.open").getByRole("button", { name: "Open uart_send in Files" }).click();
  await expect(tab(page, "Files")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator('.bd-viewer .fsec[data-path="//fixture/driver/uart.c"]')).toBeVisible();
  await expect(page.locator(".bd-viewer .bd-ln.focus")).toContainText("int uart_send");
  await page.locator(".bd-viewer").getByRole("button", { name: "Close all" }).click();
  await expect(page.locator(".ph-pick")).toContainText("uart.c");
  await expect(page.locator(".ph-pick")).toContainText("logger.c");                 // files with side effects

  // Summary: the change panel, with side-effect files that open in Files
  await tab(page, "Summary").click();
  const summary = page.locator(".bd-about");
  await expect(summary.getByText("Files with side effects")).toBeVisible();
  await summary.locator(".fx-fn", { hasText: "logger_flush" }).click();
  await expect(tab(page, "Files")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator('.bd-viewer .fsec[data-path="//fixture/service/logger.c"]')).toBeVisible();

  // Map shows the graph; the review menu holds the other pages
  await tab(page, "Map").click();
  await expect(page.locator(".bd-node").first()).toBeVisible();
  await page.getByRole("button", { name: "Review menu" }).click();
  await expect(page.locator(".ph-menu").getByRole("link", { name: /Findings/ })).toBeVisible();
  await expect(page.locator(".ph-menu .theme-switch")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});

test("the phone tab is remembered for the review", async ({ page }) => {
  await startReview(page);
  await tab(page, "Summary").click();
  await page.reload();
  await expect(tab(page, "Summary")).toHaveAttribute("aria-selected", "true");
});
