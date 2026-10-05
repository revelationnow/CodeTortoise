import { devices, expect, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startReview } from "./helpers";

/** The workspace shell (spec 2026-10-04-review-workspace §2): rail, breadcrumb, addresses, phone levels. */

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the rail lists the review, its CLs, the stories drawn from them, findings and files", async ({ page }) => {
    const base = await startReview(page);
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
    await expect(crumbs.locator("[aria-current=page]")).toContainText("uart_send can now return -2");
    await crumbs.getByRole("link", { name: "Go to Stories" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}#stories$`));
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("the whole change: what it is for, why it is risky, then the rest", async ({ page }) => {
    const base = await startReview(page);
    const page_ = page.locator(".ws-whole");
    await expect(page_.locator("h2")).toHaveText(["What this change is trying to do", "Why it is high risk",
                                                  /^The map/, "Files with side effects", "Discussion"]);
    await expect(page_.locator(".ws-summary")).toContainText("2 behaviour stories.");
    await page_.getByRole("link", { name: /^Go to finding F1:/ }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/f/F1$`));
    await page.goBack();
    await page_.locator(".ws-fx").getByRole("link", { name: /^Open uart_errors at line/ }).click();
    await expect(page).toHaveURL(/\?open=file%3A%2F%2Ffixture%2Fdriver%2Fuart\.c%3A\d+$/);
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("an address to something that does not exist says so", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/s/S9`);
    await expect(page.locator(".ws-centre .banner")).toContainText("Story S9 isn't in this review.");
    await page.getByRole("link", { name: "Whole change" }).last().click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
  });

  test("the rail keeps its closed sections and its width across a reload", async ({ page }) => {
    await startReview(page);
    const rail = page.locator(".ws-rail");
    await rail.getByRole("button", { name: /^Findings/ }).click();
    await expect(rail.getByRole("button", { name: /^Findings/ })).toHaveAttribute("aria-expanded", "false");
    const grip = rail.locator(".bd-resizer");
    const g = (await grip.boundingBox())!, w = (await rail.boundingBox())!.width;
    await page.mouse.move(g.x + g.width / 2, g.y + 200);
    await page.mouse.down();
    await page.mouse.move(g.x + g.width / 2 + 80, g.y + 200, { steps: 5 });
    await page.mouse.up();
    await expect.poll(async () => (await rail.boundingBox())!.width).toBeGreaterThan(w + 60);
    const wider = (await rail.boundingBox())!.width;
    await page.reload();
    await expect(rail.getByRole("button", { name: /^Findings/ })).toHaveAttribute("aria-expanded", "false");
    await expect(rail.getByRole("button", { name: /^Stories/ })).toHaveAttribute("aria-expanded", "true");
    expect(Math.abs((await rail.boundingBox())!.width - wider)).toBeLessThan(2);
  });

  test("Back from a review that does not exist shows the review before it", async ({ page }) => {
    const base = await startReview(page);
    const title = await page.locator(".ws-head h1").innerText();
    await page.evaluate(() => { history.pushState(null, "", "/r/999999"); dispatchEvent(new PopStateEvent("popstate")); });
    await expect(page.locator("main.page.error")).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await expect(page.locator(".ws-head h1")).toHaveText(title);
  });
});

test.describe("tablet", () => {
  test.use({ viewport: { width: 900, height: 1000 } });

  test("the rail is a drawer behind ☰", async ({ page }) => {
    await startReview(page);
    const rail = page.locator(".ws-rail");
    await expect(rail).not.toBeInViewport();
    await page.getByRole("button", { name: "Review contents" }).click();
    await expect(rail).toBeInViewport();
    await rail.getByRole("link", { name: /^Go to story S2/ }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
    await expect(rail).not.toBeInViewport();
  });

  test("the closed drawer is out of the keyboard's way", async ({ page }) => {
    await startReview(page);
    const menu = page.getByRole("button", { name: "Review contents" });
    const inRail = () => page.evaluate(() => !!document.activeElement?.closest(".ws-rail"));
    await menu.focus();
    for (let i = 0; i < 4; i++) { await page.keyboard.press("Tab"); expect(await inRail()).toBe(false); }
    await menu.click();
    await page.locator(".ws-rail").getByRole("link", { name: "Go to the whole change" }).focus();
    expect(await inRail()).toBe(true);
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the rail is home; an item's top bar names where it came from", async ({ page }) => {
    const base = await startReview(page);
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

  test("#map opens the whole change at its map, not the rail", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}#map`);
    await expect(page.getByRole("region", { name: "The map" })).toBeInViewport();
    await expect(page.locator(".ws-rail")).toHaveCount(0);
  });
});

test.describe("a large change", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });

  test("the whole change maps its parts; a part opens its page", async ({ page }) => {
    const base = await startReview(page, "201 202");
    const map = page.getByRole("region", { name: "The map" });
    await expect(map.locator(".ov-block")).toHaveCount(7);
    await expect(map.getByRole("region", { name: "Layer drv" })).toContainText("drv/dma");
    const tints = await map.locator(".ov-band").evaluateAll((els) => els.map((e) => getComputedStyle(e).backgroundColor));
    expect(new Set(tints).size).toBeGreaterThan(1);   // each layer band keeps its level tint
    const gaps = await map.locator(".ov-band").evaluateAll((els) => els.map((e) => getComputedStyle(e).marginBottom));
    expect(new Set(gaps)).toEqual(new Set(["8px"]));      // bands sit close; only the page's own sections are spaced apart
    await map.getByRole("link", { name: "Open drv/uart" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/c/C\\d+$`));
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Map › drv/uart");
    await expect(page.locator(".bd-node").first()).toBeVisible();
    await expect(page.getByRole("region", { name: "Flow" })).toBeVisible();
    let visitor = page.locator(".bd-home").first();
    for (let i = 0; i < 7 && !(await visitor.count()); i++) {          // step through the parts to one with a visitor
      await page.getByRole("link", { name: /^Next part:/ }).click();
      await expect(page.locator(".bd-node").first()).toBeVisible();
      visitor = page.locator(".bd-home").first();
    }
    expect(await visitor.count(), "no part of the large fixture shows a visitor from another part").toBeGreaterThan(0);
    const to = (await visitor.getAttribute("aria-label"))!.replace(/^Go to /, "");   // a visitor links to its own part
    await visitor.dispatchEvent("pointerdown", { bubbles: true, pointerId: 1, button: 0 });
    await visitor.dispatchEvent("pointerup", { bubbles: true, pointerId: 1, button: 0 });
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText(`Map › ${to}`);
    await expect(page).toHaveURL(/open=N\d+$/);
  });
});

test.describe("a large change on a phone", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("the map stacks the parts; a part opens with its place among them", async ({ page }) => {
    await startReview(page, "201 202");
    await page.locator(".ws-rail").getByRole("link", { name: "Go to the whole change" }).click();
    const first = page.locator(".ov-block").first(), second = page.locator(".ov-block").nth(1);
    const a = (await first.boundingBox())!, b = (await second.boundingBox())!;
    expect(b.y).toBeGreaterThan(a.y + a.height - 1);                      // stacked, not side by side
    expect(a.width).toBeGreaterThan(300);
    await expect(first).toHaveAttribute("aria-label", /^Open /);    // each part is a link to its page
    await first.click();
    await expect(page.locator(".bd-node").first()).toBeVisible();
    await expect(page.getByRole("link", { name: /^Next part:/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Back to Map/ })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
