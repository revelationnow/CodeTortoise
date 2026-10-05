import { devices, expect, test } from "@playwright/test";
import { login, startReview } from "./helpers";

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("landing page: start a review, search and filter reviews", async ({ page }) => {
    // the e2e server is shared by the whole run, so other tests' reviews are in the list too
    const title = `flags field only ${Date.now()}`;
    await startReview(page);
    await page.goto("/");
    await page.getByLabel("Changelists (shelved or submitted)").fill("102");
    await page.getByLabel("Title (optional)").fill(title);
    await page.getByRole("button", { name: "Start review" }).click();
    await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story/ }).first()).toBeVisible({ timeout: 60_000 }); // a review opens on its workspace
    await page.getByRole("link", { name: "Reviews" }).first().click();

    const rows = page.locator(".rv-list .rv-row");
    await expect(rows.first()).toBeVisible();
    const total = await rows.count();
    const search = page.getByRole("searchbox", { name: "Search reviews" });
    await search.fill(title.split(" ").at(-1)!);                                       // the unique part of the title
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText(title);
    await expect(page.getByText(`1 of ${total} reviews`)).toBeVisible();
    await search.fill("flags field");
    await expect(rows.first().locator("mark").first()).toHaveText(/flags/i);
    await search.press("Escape");
    await expect(rows).toHaveCount(total);
    await search.fill("101");                                                         // a CL number
    // wait for the filter itself: no row may remain without CL 101 (reading rows.all() first raced the re-render)
    await expect(rows.filter({ hasNot: page.locator(".cl", { hasText: "101" }) })).toHaveCount(0);
    await expect(rows.first()).toBeVisible();
    await search.fill("");
    const high = page.getByRole("button", { name: /^High risk/ });
    const n = Number((await high.locator("span").textContent())!.trim());
    await high.click();
    await expect(rows).toHaveCount(n);
    for (const r of await rows.all()) await expect(r.locator(".rv-risk")).toHaveText("HIGH");
    await page.getByRole("button", { name: /^Mine/ }).click();
    await expect(rows).toHaveCount(total);                                            // every review here was started by demo
  });

  test("the logo is in the top bar and the tab; /new goes to the landing page", async ({ page }) => {
    await login(page);
    await expect(page.locator(".topbar .brand svg")).toBeVisible();
    expect(await page.locator('link[rel="icon"]').getAttribute("href")).toBe("/logo.svg");
    expect((await page.request.get("/logo.svg")).headers()["content-type"]).toContain("svg");
    await page.goto("/new");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "Review a change" })).toBeVisible();
  });

  test("viewers who are not the owner see a welcome instead of the form", async ({ page }) => {
    await login(page, "bob");
    await expect(page.getByLabel("Changelists (shelved or submitted)")).toHaveCount(0);
    await expect(page.locator(".rv-hello")).toContainText("bob");
  });

  test("login is a card with the mascot", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator(".login-card svg")).toBeVisible();
    await expect(page.locator(".login-card").getByLabel("P4 user")).toBeVisible();
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("landing fits the screen and the menu holds the links", async ({ page }) => {
    await login(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await expect(page.getByRole("link", { name: "Health" })).toBeHidden();
    await page.getByRole("button", { name: "Menu" }).click();
    await expect(page.getByRole("link", { name: "Health" })).toBeVisible();
    await page.getByRole("link", { name: "Health" }).click();
    await expect(page.getByRole("heading", { name: /Health/ })).toBeVisible();
  });
});
