import { devices, expect, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, flowStripHolds, startWorkspace } from "./helpers";

/** A story in the workspace (spec 2026-10-04-review-workspace §3.2, §2.4). */

const step = (page: Page, label: string) => page.getByRole("list", { name: "Flow steps" }).getByRole("link", { name: `Open ${label}'s code` });
const node = (page: Page, label: string) => page.locator(".bd-node", { has: page.locator(".lbl", { hasText: new RegExp(`^${label}$`) }) });

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("steps open the detail panel and mark the step; flows replace history; findings link to their pages", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page.locator(".ws-story-head h2")).toContainText("uart_send now writes Uart::errors");
    await expect(page.getByRole("tab", { name: "Steps" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".ws-story-meta .ws-chip")).toHaveText(["CL 101"]);
    await step(page, "uart_send").click();
    await expect(page).toHaveURL(/\/s\/S1\?open=N\d+$/);
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Close uart_send's code" })).toHaveAttribute("aria-current", "true");
    await page.getByRole("link", { name: "Close uart_send's code" }).click();
    await expect(page.locator(".ws-detail")).toHaveCount(0);

    await flowStripHolds(page);
    await page.goBack();                                       // flows replaced the entry: Back undoes the close
    await expect(page.locator(".ws-detail")).toBeVisible();
    await page.goForward();
    await page.getByRole("link", { name: /^Go to finding F1:/ }).first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/f/F1$`));
    await expectNoNodeIds(page);
  });

  test("the graph: a node click opens and closes its code; ‹ › keep their place between stories", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}/s/S1`);
    await page.getByRole("tab", { name: "Graph" }).click();
    await expect(page).toHaveURL(/\/s\/S1\?view=graph$/);
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Graph");
    await node(page, "uart_send").click();
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await node(page, "uart_send").click();
    await expect(page.locator(".ws-detail")).toHaveCount(0);
    await flowStripHolds(page);
    await expectNamed(page);

    await page.getByRole("tab", { name: "Steps" }).click();
    await expect(page.getByRole("list", { name: "Flow steps" })).toBeVisible();     // measure in the Steps layout
    const next = page.getByRole("link", { name: /^Next story/ });
    const x = (await next.boundingBox())!.x;
    await next.click();
    await expect(page).toHaveURL(/\/s\/S2$/);
    await expect(page.locator(".ws-story-head h2")).toContainText("hal_write");
    expect((await page.getByRole("link", { name: /^Next story/ }).boundingBox())!.x).toBe(x);
  });

  test("leaving a story for a CL and coming back returns to the same view, flow and open node", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}/s/S1?view=graph`);
    await page.getByRole("button", { name: "Next flow" }).click();
    await node(page, "uart_send").click();
    await expect(page).toHaveURL(/view=graph&flow=2&open=N\d+$/);
    const there = page.url();
    await page.locator(".ws-rail").getByRole("link", { name: "Open CL 101" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/cl/101$`));
    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page).toHaveURL(there);
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await expect(page.locator(".ws-flow-pos")).toHaveText("flow 2 of 2");
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("rail → story → detail sheet, each top bar naming the place", async ({ page }) => {
    await startWorkspace(page);
    await page.getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page.locator(".ws-phonebar")).toContainText("‹ Stories");
    await step(page, "uart_send").click();
    const bar = page.locator(".ws-detail .ws-phonebar");
    await expect(bar).toContainText("‹ S1");
    await expect(bar).toContainText("uart_send");
    await bar.getByRole("link", { name: "Close the code" }).click();
    await expect(page.locator(".ws-centre .ws-phonebar")).toContainText("‹ Stories");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
