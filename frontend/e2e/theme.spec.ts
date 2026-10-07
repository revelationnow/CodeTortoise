import { expect, type Page, test } from "@playwright/test";
import { contrast, startReview } from "./helpers";

test.use({ viewport: { width: 1440, height: 900 } });

/** A changed function of story S1 (its first step), to open in the detail panel. */
async function firstChanged(page: Page) {
  const id = page.url().match(/\/r\/(\d+)/)![1];
  const s1 = await (await page.request.get(`/api/reviews/${id}/stories/S1`)).json();
  return s1.board.nodes.find((n: { change: unknown }) => n.change).id as string;
}

const CHECKS = [
  ".ws-flow-text p",               // flow summary text
  ".bd-node:not(.chg) .lbl",       // node label (changed nodes sit on a fixed amber gradient)
  ".ws-detail .bd-code .src",      // code in the detail panel
  ".bd-ann .k",                    // annotation label
  ".ws-row-title",                 // a rail row
  ".ws-crumbs a",                  // a breadcrumb
  ".bd-toolbar .bd-ibtn",          // a graph button
  ".topbar a",                     // app chrome link
  ".ws-rail .ct-headline",         // what to act on, in the rail
  ".ws-head .ct-headline",         // what to act on
];

for (const theme of ["light", "dark"] as const) {
  test(`readable controls and text in ${theme} mode`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    const base = await startReview(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);      // follows the system by default
    await page.goto(`${base}/s/S1?view=graph&open=${await firstChanged(page)}`);
    await expect(page.locator(".ws-detail .bd-code .src").first()).toBeVisible();
    await expect(page.locator(".bd-node").first()).toBeVisible();
    for (const sel of CHECKS) expect(await contrast(page, sel), sel).toBeGreaterThanOrEqual(4.5);
    await page.goto("/");
    const input = page.getByRole("searchbox", { name: "Search reviews" });            // on the page surface
    expect(await input.evaluate((el) => getComputedStyle(el).colorScheme)).toContain(theme);
    for (const sel of ["textarea", ".rv-search input", ".rv-row b", ".rv-hello h1", ".rv-head h2", ".topbar a"])
      expect(await contrast(page, sel), sel).toBeGreaterThanOrEqual(4.5);
    await page.goto("/health");
    for (const sel of [".hc-row b", ".hc-row .detail"]) expect(await contrast(page, sel), sel).toBeGreaterThanOrEqual(4.5);
  });
}

test("the theme switch overrides the system and is remembered", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await startReview(page);
  await page.getByRole("button", { name: "Dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "System theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.emulateMedia({ colorScheme: "dark" });                                  // live OS change
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});
