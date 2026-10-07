import { devices, expect, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startReview } from "./helpers";

/** The workspace shell (spec 2026-10-04-review-workspace §2): rail, breadcrumb, addresses, phone levels. */

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the rail lists the overview, the thread's stories, what may be missed and the Index", async ({ page }) => {
    const base = await startReview(page);
    const rail = page.locator(".ws-rail");
    await expect(rail.locator(".ws-sec h2")).toHaveText([/Threads \(1\)$/, "Index"]);
    await expect(rail.getByRole("link", { name: "Go to the overview" })).toHaveAttribute("aria-current", "page");
    const home = (await rail.locator(".ws-home").boundingBox())!, first = (await rail.locator(".ws-sec-t").first().boundingBox())!;
    expect(first.y - (home.y + home.height)).toBeLessThan(12);               // sections follow on: the grip takes no room
    await expect(rail.locator(".ws-index-row")).toHaveText(["CLs", "Files", "Checks", "Map"]);
    const s1 = rail.getByRole("link", { name: /^Go to story S1/ });
    await s1.click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await expect(s1).toHaveAttribute("aria-current", "page");
    const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
    await expect(crumbs).toContainText("Thread A");
    await expect(crumbs.locator("[aria-current=page]")).toContainText("uart_send can now return -2");
    await crumbs.getByRole("link", { name: "Go to Thread A" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("the overview: the change as a whole, its one thread and what to check", async ({ page }) => {
    await startReview(page);
    const left = page.locator(".ov2-left");
    await expect(left.locator("h2")).toHaveText(["The change as a whole", "How the threads connect", "Threads", "Discussion"]);
    await expect(left.locator(".ws-lead")).toHaveText("One thread: hal_write in hal.");
    await expect(left).toContainText("One thread: all stories are connected by calls or shared data.");
    await expect(page.getByRole("region", { name: "To check" }).locator(".ck-row")).toHaveCount(5);
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("the header says what to act on in place of the risk pill", async ({ page }) => {
    await startReview(page);
    const head = page.locator(".ws-head");
    await expect(head.locator(".ct-headline")).toHaveText("Medium risk · rules only");   // header fan-out never raises it
    await expect(head.locator(".bd-pill.high")).toHaveCount(0);
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
    await rail.getByRole("button", { name: /^Threads/ }).click();
    await expect(rail.getByRole("button", { name: /^Threads/ })).toHaveAttribute("aria-expanded", "false");
    const grip = rail.locator(".bd-resizer");
    const g = (await grip.boundingBox())!, w = (await rail.boundingBox())!.width;
    await page.mouse.move(g.x + g.width / 2, g.y + 200);
    await page.mouse.down();
    await page.mouse.move(g.x + g.width / 2 + 80, g.y + 200, { steps: 5 });
    await page.mouse.up();
    await expect.poll(async () => (await rail.boundingBox())!.width).toBeGreaterThan(w + 60);
    const wider = (await rail.boundingBox())!.width;
    await page.reload();
    await expect(rail.getByRole("button", { name: /^Threads/ })).toHaveAttribute("aria-expanded", "false");
    expect(Math.abs((await rail.boundingBox())!.width - wider)).toBeLessThan(2);
  });

  test("the rail's grip straddles its border, clear of its scrollbar, and drags from there", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 300 });
    await startReview(page);
    const rail = page.locator(".ws-rail");
    expect(await rail.evaluate((e) => { const s = e.querySelector(".ws-rail-scroll") ?? e; return s.scrollHeight > s.clientHeight; })).toBe(true);
    const r = (await rail.boundingBox())!, x = r.x + r.width + 3, y = r.y + r.height / 2;   // just past the border
    expect(await page.evaluate(([px, py]) => !!document.elementFromPoint(px, py)?.closest(".bd-resizer"), [x, y])).toBe(true);
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + 80, y, { steps: 5 });
    await page.mouse.up();
    await expect.poll(async () => (await rail.boundingBox())!.width).toBeGreaterThan(r.width + 60);
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
    await page.locator(".ws-rail").getByRole("link", { name: "Go to the overview" }).focus();
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
    await expect(bar).toContainText("‹ Thread A");
    await expect(bar).toContainText("S1");
    await bar.getByRole("link", { name: "Back to Thread A" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await expect(page.locator(".ws-rail")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });

  test("#map opens the Index at its map, not the rail", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}#map`);
    await expect(page).toHaveURL(new RegExp(`${base}/i/map$`));
    await expect(page.getByRole("region", { name: "The map" })).toBeInViewport();
    await expect(page.locator(".ws-rail")).toHaveCount(0);
  });
});

test.describe("a large change", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });

  test("the Index maps the change's parts; a part opens its page", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Map" }).click();
    const map = page.getByRole("region", { name: "The map" });
    await expect(map.locator(".ov-block")).toHaveCount(7);
    await expect(map.locator(".ov-block .ct").filter({ hasText: /\b0 \w/ })).toHaveCount(0);      // an empty count is never shown
    await expect(map.getByRole("region", { name: "Layer drv" })).toContainText("drv/dma");
    const tints = await map.locator(".ov-band").evaluateAll((els) => els.map((e) => getComputedStyle(e).backgroundColor));
    expect(new Set(tints).size).toBeGreaterThan(1);   // each layer band keeps its level tint
    const gaps = await map.locator(".ov-band").evaluateAll((els) => els.map((e) => getComputedStyle(e).marginBottom));
    expect(new Set(gaps)).toEqual(new Set(["8px"]));      // bands sit close; only the page's own sections are spaced apart
    await map.getByRole("link", { name: "Open drv/uart" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/c/C\\d+$`));
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Map › drv/uart");
    await expect(page.locator(".ws-story-meta")).not.toContainText(/\b0 \w/);
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
    await page.locator(".ws-rail").getByRole("link", { name: "Open the Index: Map" }).click();
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
