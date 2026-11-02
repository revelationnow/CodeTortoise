import { expect, type Page } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startReview, test } from "./helpers";

/** The design overview's walk-throughs (spec 2026-11-02 §3, §4, §18). CLs 101–104 have four: W1 takes `len > 64` from `main`
 * through `logger_flush` into `uart_send`, returns -2 to `logger_flush` (S1's flow 1) and reaches the reader `uart_errors`
 * (S1's flow 2), on the connection between Thread A and Thread B. */
const FOUR = "101 102 103 104";
const STEP5 = "Looks fine: step 5, uart_send returns -2 to logger_flush";

const steps = (page: Page) => page.locator(".dz-walk ol.fl-rows > li.fl-row");

test.describe("a walk-through's page", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("reads as a story does: its crumbs and head, then its steps, each saying where it comes from", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/walk/W1`);
    await expect(page.locator(".ws-crumbs")).toHaveText(/ › Thread A with Thread B › Walk through: When len > 64$/);
    const head = page.locator(".dz-walk .st-head");
    await expect(head.locator("h2")).toHaveText("When len > 64");
    await expect(head.locator(".st-crumb")).toHaveText("Thread A with Thread B · 9 steps · over S1 · 2 open");
    await expect(head.locator(".dz-note")).toHaveText(/^Built from the stories' call paths and flows; the arrows are calls/);
    await expect(steps(page)).toHaveCount(9);
    await expect(steps(page).locator(".fl-one")).toHaveText([
      "main calls logger_flush(&g_log)", 'logger_flush calls uart_send(lg->uart, "\\n", 1)', "uart_send: len > 64",
      "uart_send writes Uart::errors: *err += 1", "uart_send returns -2 to logger_flush", "logger_flush returns to main",
      "main calls uart_errors(&g_uart)", "uart_errors reads Uart::errors: u->errors", "uart_errors returns u->errors to main"]);
    await expect(steps(page).locator(".dz-ref")).toHaveText([
      "call path of S1 flow 1 ›", "call path of S1 flow 1 ›", "S1 · the change ›", "S1 · the change ›", "S1 flow 1 ›",
      "logger_flush, unchanged", "main, unchanged", "S1 flow 2 ›", "uart_errors, unchanged"]);
    await expect(steps(page).locator(".fl-tick")).toHaveCount(2);                     // steps 5 and 8, the flows
    await expect(page.getByRole("region", { name: "Other walk-throughs" }).locator(".st-chip")).toHaveText([
      "▶ When len > 64 is false", "▶ From main through hal_write", "▶ From main through logger_init"]);
    await expectNoNodeIds(page);
    await expectNamed(page);
    await page.getByRole("link", { name: "Go to call path of S1 flow 1" }).first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1\\?sec=paths$`));
  });

  test("marking a step fine marks its flow fine everywhere: the story's row, the walk-through's count and the head's", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/walk/W1`);
    const progress = page.locator(".ws-progress"), crumb = page.locator(".dz-walk .st-crumb");
    await expect(progress).toHaveText("0 of 5 stories read · 4 checks open");
    await page.getByRole("checkbox", { name: STEP5 }).click();                 // checked once the mark lands, as a Flows row's box
    await expect(progress).toHaveText("0 of 5 stories read · 3 checks open");
    await expect(page.getByRole("checkbox", { name: STEP5 })).toBeChecked();
    await expect(crumb).toHaveText(/ · 1 open$/);
    await page.getByRole("link", { name: "Go to S1 flow 1" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1\\?flow=1$`));
    await expect(page.locator("#flow-1 .fl-tick")).toBeChecked();
    await page.goBack();
    await page.getByRole("checkbox", { name: STEP5 }).click();
    await expect(progress).toHaveText("0 of 5 stories read · 4 checks open");
    await expect(crumb).toHaveText(/ · 2 open$/);
  });

  test("?step=N opens that step; a step or a walk-through the review does not have is no error", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/walk/W1?step=8`);
    const row = page.locator("#step-8");
    await expect(row.locator(".fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await expect(row.locator(".fl-path")).toHaveText(/^driver\/uart\.c:\d+$/);
    await expect(row.locator(".fl-check")).toHaveCount(1);                            // the reader row's check
    await page.goto(`${base}/walk/W1?step=99`);
    await expect(steps(page)).toHaveCount(9);
    await expect(page.locator(".dz-walk .fl-toggle[aria-expanded='true']")).toHaveCount(0);
    await page.goto(`${base}/walk/W9`);
    await expect(page.locator(".ws-centre .banner.warn")).toHaveText("This walk-through isn't in this review. Whole change");
  });

  test("J and K step through the steps and F marks the one with focus fine, then moves to the next still open", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/walk/W1?step=4`);
    await expect(page.locator("#step-4 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await page.locator("#step-4 .fl-toggle").focus();
    await page.keyboard.press("j");
    await expect(page.locator("#step-5 .fl-toggle")).toBeFocused();
    await page.keyboard.press("f");
    await expect(page.locator("#step-5 .fl-tick")).toBeChecked();
    await expect(page.locator("#step-8 .fl-toggle")).toBeFocused();
    await page.keyboard.press("k");
    await expect(page.locator("#step-7 .fl-toggle")).toBeFocused();
  });
});
