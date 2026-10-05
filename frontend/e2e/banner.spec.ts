import { devices, expect, test } from "@playwright/test";
import { login, startReview } from "./helpers";

// a second name for the e2e server that is not loopback (spec §14.5); 127.0.0.1 itself is unaffected
test.use({ launchOptions: { args: ["--host-resolver-rules=MAP ct-lan.test 127.0.0.1"] } });

const banner = "Not encrypted — this connection to CodeTortoise is plain HTTP over the network.";

test("no plain-HTTP banner on a loopback address", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await expect(page.getByText(banner)).toHaveCount(0);
});

test.describe("on a network host name", () => {
  test.use({ baseURL: "http://ct-lan.test:8799" });

  test("the plain-HTTP banner shows on the login page and on a review", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("alert")).toHaveText(banner);
    await login(page);
    await startReview(page);
    await expect(page.getByRole("alert")).toHaveText(banner);
  });

  test.describe("on a phone", () => {
    test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent, isMobile: true, hasTouch: true });

    test("the banner and the phone workspace fit the screen together", async ({ page }) => {
      await startReview(page);
      await expect(page.getByRole("alert")).toBeVisible();
      await page.locator(".ws-rail").getByRole("link", { name: /^Go to story/ }).first().click();
      const bar = (await page.locator(".ws-phonebar").boundingBox())!;
      expect(bar.y).toBeGreaterThanOrEqual(0);                                             // the back bar stays on screen
      expect(bar.y + bar.height).toBeLessThanOrEqual(page.viewportSize()!.height);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    });
  });
});
