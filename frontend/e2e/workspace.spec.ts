import { devices, expect, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startWorkspace } from "./helpers";

/** The workspace shell (spec 2026-10-04-review-workspace §2): rail, breadcrumb, addresses, phone levels. */

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the rail lists the review, its CLs, the stories drawn from them, findings and files", async ({ page }) => {
    const base = await startWorkspace(page);
    const rail = page.locator(".ws-rail");
    await expect(rail.locator(".ws-sec h2")).toHaveText([/Change set \(2 CLs\)/, /Stories \(from 2 CLs\)/, /Findings \(6\)/, /Files \(4\)/]);
    await expect(rail.getByRole("link", { name: "Go to the whole change" })).toHaveAttribute("aria-current", "page");
    const home = (await rail.locator(".ws-home").boundingBox())!, first = (await rail.locator(".ws-sec-t").first().boundingBox())!;
    expect(first.y - (home.y + home.height)).toBeLessThan(12);               // sections follow on: the grip takes no room
    const s1 = rail.getByRole("link", { name: /^Go to story S1/ });
    await expect(s1.locator(".ws-chip")).toHaveText(["CL 101"]);

    // the CL filter lights the stories drawn from it and dims the rest; again clears it
    await rail.getByRole("button", { name: "Highlight the stories drawn from CL 102" }).click();
    await expect(s1).toHaveClass(/\bdim\b/);
    await expect(rail.getByRole("link", { name: /^Go to story S2/ })).not.toHaveClass(/\bdim\b/);
    await rail.getByRole("button", { name: "Show every story" }).click();
    await expect(s1).not.toHaveClass(/\bdim\b/);

    await s1.click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await expect(s1).toHaveAttribute("aria-current", "page");
    const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
    await expect(crumbs).toContainText("Stories");
    await expect(crumbs.locator("[aria-current=page]")).toContainText("uart_send now writes Uart::errors");
    await crumbs.getByRole("link", { name: "Go to Stories" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}#stories$`));
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("an address to something that does not exist says so", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}/s/S9`);
    await expect(page.locator(".ws-centre .banner")).toContainText("Story S9 isn't in this review.");
    await page.getByRole("link", { name: "Whole change" }).last().click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
  });
});

test.describe("tablet", () => {
  test.use({ viewport: { width: 900, height: 1000 } });

  test("the rail is a drawer behind ☰", async ({ page }) => {
    await startWorkspace(page);
    const rail = page.locator(".ws-rail");
    await expect(rail).not.toBeInViewport();
    await page.getByRole("button", { name: "Review contents" }).click();
    await expect(rail).toBeInViewport();
    await rail.getByRole("link", { name: /^Go to story S2/ }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
    await expect(rail).not.toBeInViewport();
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the rail is home; an item's top bar names where it came from", async ({ page }) => {
    const base = await startWorkspace(page);
    await expect(page.locator(".topbar")).toBeHidden();
    await expect(page.locator(".ws-centre")).toHaveCount(0);
    await page.getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page.locator(".ws-rail")).toHaveCount(0);
    const bar = page.locator(".ws-phonebar");
    await expect(bar).toContainText("‹ Stories");
    await expect(bar).toContainText("S1");
    await bar.getByRole("link", { name: "Back to Stories" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}#stories$`));
    await expect(page.locator(".ws-rail")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
