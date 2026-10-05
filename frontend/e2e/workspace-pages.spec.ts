import { expect, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startWorkspace } from "./helpers";

/** Finding, CL and cluster pages (spec 2026-10-04-review-workspace §3.3–§3.5). */

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a finding: to its story and back, on the graph, evidence opens the diff at its line", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.goto(`${base}/f/F5`);
    await expect(page.locator(".ws-finding h2")).toContainText("uart_send: new return value(s) -2");
    await expect(page.getByRole("region", { name: "AI analysis" })).toContainText("AI analysis unavailable.");
    await page.getByRole("link", { name: /^Go to story S1/ }).first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`${base}/f/F5$`));

    await page.getByRole("link", { name: "Open service/logger.c at line 12" }).first().click();
    await expect(page).toHaveURL(/open=file%3A%2F%2Ffixture%2Fservice%2Flogger\.c%3A12$/);
    await expect(page.getByRole("complementary", { name: "Code: logger.c" }).locator('[data-n="12"]').first()).toBeVisible();
    await page.goBack();

    await page.getByRole("link", { name: "Show it on the graph" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1\\?view=graph&open=N\\d+$`));
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await page.goBack();

    await page.getByRole("link", { name: /^Next finding: F6/ }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/f/F6$`));
    await page.getByRole("button", { name: "mark acknowledged" }).click();
    await expect(page.locator(".ws-finding .ws-badge")).toHaveText("acknowledged");
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("a changelist: its Swarm card, its files filtered to it, the stories and findings drawn from it", async ({ page }) => {
    const base = await startWorkspace(page);
    await page.locator(".ws-rail").getByRole("link", { name: "Open CL 102" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/cl/102$`));
    await expect(page.locator(".ws-finding h2")).toHaveText("CL 102 · uart: add flags field; hal_write takes unsigned reg");
    await expect(page.getByRole("region", { name: "Swarm" })).toContainText("No Swarm review.");
    await expect(page.getByRole("region", { name: "Swarm" }).getByRole("button", { name: "Refresh" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Stories drawn from this CL" })).toContainText("hal_write");
    await page.getByRole("link", { name: "Open regs.c's diff in CL 102" }).click();
    await expect(page.getByRole("complementary", { name: "Code: regs.c" }).getByLabel("Changelist")).toHaveValue("102");
    await expectNoNodeIds(page);
    await expectNamed(page);
  });
});
