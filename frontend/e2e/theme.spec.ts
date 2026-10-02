import { expect, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

test.use({ viewport: { width: 1440, height: 900 } });

/** WCAG contrast ratio between an element's text colour and the first opaque background behind it. */
async function contrast(page: Page, selector: string) {
  return page.locator(selector).first().evaluate((el) => {
    const rgb = (c: string) => (c.match(/[\d.]+/g) ?? []).map(Number);
    const lum = ([r, g, b]: number[]) => {
      const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    let bgEl: Element | null = el, bg = "";
    while (bgEl) {
      const c = getComputedStyle(bgEl).backgroundColor, a = rgb(c)[3];
      if (c && c !== "transparent" && (a === undefined || a > 0.9)) { bg = c; break; }
      bgEl = bgEl.parentElement;
    }
    const fg = lum(rgb(getComputedStyle(el).color)), b = lum(rgb(bg || "rgb(255,255,255)"));
    return (Math.max(fg, b) + 0.05) / (Math.min(fg, b) + 0.05);
  });
}

const CHECKS = [
  ".bd-flowinfo .what",            // flow summary text
  ".bd-node:not(.chg) .lbl",       // node label (changed nodes sit on a fixed amber gradient)
  ".bd-card .bd-code .src",        // code in a card
  ".bd-ann .k",                    // annotation label
  ".bd-about .intent",             // change panel text
  ".bd-toolbar .bd-ibtn",          // a board button
  ".topbar a",                     // app chrome link
];

for (const theme of ["light", "dark"] as const) {
  test(`readable controls and text in ${theme} mode`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await startReview(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);      // follows the system by default
    await expect(page.locator(".bd-card .bd-code .src").first()).toBeVisible();
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
