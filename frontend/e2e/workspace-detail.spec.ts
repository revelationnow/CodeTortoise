import { devices, expect, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startWorkspace } from "./helpers";

/** The detail panel (spec 2026-10-04-review-workspace §3.7): a node's code or a file's diff, on demand. */

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a file from the rail opens its diff; ✕ closes it", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
    await expect(page).toHaveURL(/\?open=file%3A%2F%2Ffixture%2Fdriver%2Fuart\.c$/);
    const panel = page.getByRole("complementary", { name: "Code: uart.c" });
    await expect(panel.locator(".ws-detail-path")).toHaveText("//fixture/driver/uart.c");
    await expect(panel.locator(".bd-code")).toBeVisible();
    await expect(panel.getByLabel("Changelist")).toHaveValue("all");
    await panel.getByRole("button", { name: "Full file" }).click();
    await expect(panel.locator(".bd-gap")).toHaveCount(0);
    await expectNamed(page);
    await panel.getByRole("link", { name: "Close the code" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await expect(page.locator(".ws-detail")).toHaveCount(0);
  });

  test("a node opens its function, its story and the full file", async ({ page }) => {
    const base = await startWorkspace(page);
    const names = await page.evaluate(async (b) => (await fetch(`/api/reviews/${b.split("/")[2]}/names`)).json(), base);
    const send = Object.entries(names as Record<string, { label: string }>).find(([, n]) => n.label === "uart_send")![0];
    await page.goto(`${base}?open=${send}`);
    const panel = page.getByRole("complementary", { name: "Code: uart_send" });
    await expect(panel.locator(".ws-badge")).toHaveText("changed");
    await expect(panel.locator(".ws-detail-path")).toContainText("//fixture/driver/uart.c · lines");
    await expect(panel.locator(".bd-code")).toBeVisible();
    await panel.getByRole("button", { name: "Full file" }).click();
    await expect(panel.getByLabel("Changelist")).toBeVisible();
    await panel.getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await expectNoNodeIds(page);
  });

  test("an unknown node says so", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}?open=N99999`);
    await expect(page.locator(".ws-detail .banner")).toContainText("This function isn't in this review.");
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the code opens as a full-screen sheet whose top bar names it", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}?open=${encodeURIComponent("file://fixture/driver/uart.c:17")}`);
    await expect(page.locator(".ws-rail, .ws-centre")).toHaveCount(0);
    const bar = page.locator(".ws-detail .ws-phonebar");
    await expect(bar).toContainText("uart.c");
    await bar.getByRole("link", { name: "Close the code" }).click();
    await expect(page.locator(".ws-detail")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
