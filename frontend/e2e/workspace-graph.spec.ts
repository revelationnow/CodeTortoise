import { expect, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, flowStripHolds, startWorkspace } from "./helpers";

/** Graphs in the workspace (spec 2026-10-04-review-workspace §3.2, §3.6): a node click opens its code and a second
 * click closes it; "+N callers" opens Neighbours; the flow strip keeps its controls in place and never overflows. */

const node = (page: Page, label: string) => page.locator(".bd-node", { has: page.locator(".lbl", { hasText: new RegExp(`^${label}$`) }) });

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the review's graph: open full graph, select and deselect a node, flows keep their controls", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.getByRole("link", { name: "Open the full graph" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}\\?view=graph$`));
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Graph");
    await flowStripHolds(page);
    await expect(page).toHaveURL(/view=graph&flow=\d$/);

    await node(page, "uart_send").click();
    await expect(page).toHaveURL(/&open=N\d+$/);
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await expect(node(page, "uart_send")).toHaveAttribute("aria-pressed", "true");
    await node(page, "uart_send").click();
    await expect(page.locator(".ws-detail")).toHaveCount(0);
    await page.goBack();
    await expect(page.locator(".ws-detail")).toBeVisible();
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("a file from the rail highlights its functions on the graph and never refilters it", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}?view=graph`);
    await expect(page.locator(".bd-node").first()).toBeVisible();
    const count = await page.locator(".bd-node").count();
    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
    await expect(page.locator(".bd-node.lit").first()).toBeVisible();
    await expect(page.locator(".bd-node")).toHaveCount(count);
  });
});
