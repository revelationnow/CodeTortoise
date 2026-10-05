import { devices, expect, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, flowStripHolds, startReview } from "./helpers";

/** Graphs in the workspace (spec 2026-10-04-review-workspace §3.2, §3.6): a node click opens its code and a second
 * click closes it; "+N callers" opens Neighbours; the flow strip keeps its controls in place and never overflows. */

/** A node the pointer reaches at its centre (the whole graph can be panned past the stage's edges). */
async function reachable(page: Page) {
  const label = await page.locator(".bd-node").evaluateAll((els) => els.find((e) => {
    const r = e.getBoundingClientRect(), hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    return hit && e.contains(hit) && !hit.closest("button:not(.bd-node)");
  })?.querySelector(".lbl")?.textContent ?? null);
  expect(label).not.toBeNull();
  return node(page, label!);
}

const node = (page: Page, label: string) => page.locator(".bd-node", { has: page.locator(".lbl", { hasText: new RegExp(`^${label}$`) }) });

/** The first node's offset from the graph's canvas: it changes when the graph pans, not when the page scrolls. */
async function offset(canvas: ReturnType<Page["locator"]>) {
  return canvas.evaluate((c) => {
    const a = c.getBoundingClientRect(), b = c.querySelector(".bd-node")!.getBoundingClientRect();
    return { x: Math.round(b.x - a.x), y: Math.round(b.y - a.y) };
  });
}

test.describe("the wheel", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("over the whole change's map a plain wheel scrolls the page; Shift pans it; the full graph pans on the wheel", async ({ page }) => {
    const base = await startReview(page);
    const map = page.locator(".ws-mapgraph .bd-canvas"), scroller = page.locator(".ws-page").first();
    await expect(map.locator(".bd-node").first()).toBeVisible();
    await page.locator(".ws-mapgraph").evaluate((e) => e.scrollIntoView({ block: "center" }));
    const box = (await map.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    const top = await scroller.evaluate((e) => e.scrollTop), at = await offset(map);
    await page.mouse.wheel(0, 200);
    await expect.poll(() => scroller.evaluate((e) => e.scrollTop)).toBeGreaterThan(top);
    expect(await offset(map)).toEqual(at);

    const box2 = (await map.boundingBox())!;
    await page.mouse.move(box2.x + box2.width / 2, box2.y + box2.height / 2);
    const top2 = await scroller.evaluate((e) => e.scrollTop);
    await page.keyboard.down("Shift");
    await page.mouse.wheel(0, 200);
    await page.keyboard.up("Shift");
    await expect.poll(() => offset(map).then((o) => o.x)).not.toBe(at.x);
    expect(await scroller.evaluate((e) => e.scrollTop)).toBe(top2);

    await page.goto(`${base}?view=graph`);
    const full = page.locator(".bd-canvas");
    await expect(full.locator(".bd-node").first()).toBeVisible();
    const fb = (await full.boundingBox())!;
    await page.mouse.move(fb.x + fb.width / 2, fb.y + fb.height / 2);
    const was = await offset(full);
    await page.mouse.wheel(0, 200);
    await expect.poll(() => offset(full).then((o) => o.y)).not.toBe(was.y);
  });
});

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the review's graph: open full graph, select and deselect a node, flows keep their controls", async ({ page }) => {
    const base = await startReview(page);
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
    const base = await startReview(page);
    await page.goto(`${base}?view=graph`);
    await expect(page.locator(".bd-node").first()).toBeVisible();
    const count = await page.locator(".bd-node").count();
    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
    await expect(page.locator(".bd-node.lit").first()).toBeVisible();
    await expect(page.locator(".bd-node")).toHaveCount(count);
  });

  test("drag a node anywhere, reset; moves are kept per layout; panning never selects text", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}?view=graph`);
    await page.getByRole("button", { name: "Whole graph" }).click();
    await expect(page.locator(".bd-node").first()).toBeVisible();
    await page.waitForTimeout(500);                                   // centring animation
    let main = await reachable(page);
    const drag = async (dx: number, dy: number) => {
      const a = (await main.boundingBox())!;
      await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
      await page.mouse.down();
      await page.mouse.move(a.x + a.width / 2 + dx, a.y + a.height / 2 + dy, { steps: 10 });
      await page.mouse.up();
      const b = (await main.boundingBox())!;
      expect(b.x - a.x).toBeGreaterThan(60);
      expect(b.y - a.y).toBeGreaterThan(20);                         // free to leave its band
    };
    await drag(160, 40);
    await expect(page).not.toHaveURL(/open=/);                        // a drag is not a click
    await expect(main).toHaveClass(/\bmoved\b/);
    await page.getByRole("button", { name: "Reset layout" }).click();
    await expect(main).not.toHaveClass(/\bmoved\b/);

    await page.getByRole("button", { name: "Call depth" }).click();
    await expect(page.locator(".bd-blabel", { hasText: "depth 0 · entry" })).toBeVisible();
    await page.waitForTimeout(500);
    main = await reachable(page);
    await drag(120, 150);
    await page.getByRole("button", { name: "Layers" }).click();
    await expect(main).not.toHaveClass(/\bmoved\b/);
    await page.getByRole("button", { name: "Call depth" }).click();
    await expect(main).toHaveClass(/\bmoved\b/);

    const stage = (await page.locator(".bd-stage").boundingBox())!;
    await page.mouse.move(stage.x + stage.width - 30, stage.y + stage.height - 40);
    await page.mouse.down();
    await page.mouse.move(stage.x + 30, stage.y + 120, { steps: 12 });
    await page.mouse.up();
    expect(await page.evaluate(() => window.getSelection()?.toString() ?? "")).toBe("");
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("pinch to zoom, tap a node for its code sheet, long-press to move it", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}?view=graph`);
    const send = page.locator(".bd-node.chg", { hasText: "uart_send" });
    await expect(send).toBeVisible();
    await page.waitForTimeout(500);
    const cdp = await page.context().newCDPSession(page);
    const touch = (type: string, pts: [number, number][]) =>
      cdp.send("Input.dispatchTouchEvent", { type, touchPoints: pts.map(([x, y], id) => ({ x, y, id })) });
    const centre = async () => { const b = (await send.boundingBox())!; return [b.x + b.width / 2, b.y + b.height / 2, b.width] as const; };

    const [x0, y0, w0] = await centre();                               // pinch out: it grows and stays under the fingers
    await touch("touchStart", [[x0 - 30, y0], [x0 + 30, y0]]);
    for (let k = 1; k <= 6; k++) await touch("touchMove", [[x0 - 30 - k * 12, y0], [x0 + 30 + k * 12, y0]]);
    await touch("touchEnd", []);
    const [x1, y1, w1] = await centre();
    expect(w1).toBeGreaterThan(w0 * 1.5);
    expect(Math.hypot(x1 - x0, y1 - y0)).toBeLessThan(40);

    await send.tap();                                                  // tap: the code opens as a sheet
    const sheet = page.getByRole("complementary", { name: "Code: uart_send" });
    await expect(sheet.locator(".bd-ann").first()).toContainText("through alias");
    await expect(sheet.locator("textarea")).toHaveCount(0);           // the tap's click must not land in the sheet
    await page.goBack();
    await expect(sheet).toHaveCount(0);

    await expect(send).toBeVisible();
    const [x2, y2] = await centre();                                   // long-press, then drag: the node moves
    await touch("touchStart", [[x2, y2]]);
    await page.waitForTimeout(600);
    for (let k = 1; k <= 5; k++) await touch("touchMove", [[x2 + k * 14, y2 + k * 10]]);
    await touch("touchEnd", []);
    await expect(send).toHaveClass(/\bmoved\b/);
  });
});
