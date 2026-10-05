import { expect, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startReview } from "./helpers";

/** Finding, CL and cluster pages (spec 2026-10-04-review-workspace §3.3–§3.5). */

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a finding: to its story and back, on the graph, evidence opens the diff at its line", async ({ page }) => {
    const base = await startReview(page);
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

  test("a finding without an explanation offers Explain only once the AI is known to be there", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    await page.route(`**/api/reviews/${rid}/ai`, async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.continue(); });
    await page.goto(`${base}/f/F5`);
    const ai = page.getByRole("region", { name: "AI analysis" });
    await expect(ai).toBeVisible();
    for (let i = 0; i < 6; i++) {
      expect(await ai.getByRole("button", { name: /Explain/ }).count()).toBe(0);
      expect(await ai.innerText()).not.toContain("Not written yet");                 // it may never be: say nothing yet
      await page.waitForTimeout(150);
    }
    await expect(ai).toContainText("AI analysis unavailable.");
  });

  test("the owner's Swarm buttons say what happened, and a new press clears the last answer", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    let n = 0;
    await page.route(`**/api/reviews/${rid}/cls/102/swarm/refresh`, async (r) => {
      if (n++ === 0) return r.fulfill({ status: 502, json: { detail: "Swarm did not answer" } });
      await new Promise((ok) => setTimeout(ok, 1000));
      return r.fulfill({ json: null });
    });
    await page.goto(`${base}/cl/102`);
    const swarm = page.getByRole("region", { name: "Swarm" });
    await swarm.getByRole("button", { name: "Refresh" }).click();
    await expect(swarm.locator(".banner")).toContainText("Swarm did not answer");
    await swarm.getByRole("button", { name: "Refresh" }).click();
    expect(await swarm.getByText("Swarm did not answer").count()).toBe(0);
    await expect(swarm.locator(".banner")).toHaveText("Swarm state refreshed");
  });

  test("a changelist: its Swarm card, its files filtered to it, the stories and findings drawn from it", async ({ page }) => {
    const base = await startReview(page);
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
