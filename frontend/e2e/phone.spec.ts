import { devices, expect, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
  deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

const tab = (page: Page, name: string) => page.locator(".ph-tabs").getByRole("tab", { name });

test("phone board: flow reader, files and summary tabs", async ({ page }) => {
  await startReview(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  await expect(page.locator(".topbar")).toBeHidden();                               // the review header is the only bar
  await expect(tab(page, "Flows")).toHaveAttribute("aria-selected", "true");

  // the first flow, as steps from entry to landing
  await expect(page.locator(".ph-title")).toHaveText("uart_errors sees a new writer of Uart::errors");
  await expect(page.locator(".ph-count")).toHaveText("1/3");
  const steps = page.locator(".ph-step");
  await expect(steps).toHaveCount(5);
  await expect(steps.nth(2)).toContainText("uart_send");
  await expect(steps.last()).toHaveClass(/\blanding\b/);
  await expect(page.locator(".ph-landing")).toContainText("Side effect lands on uart_errors");

  // swipe to the next flow, button back
  const box = (await page.locator(".ph-reader").boundingBox())!;
  await page.mouse.move(box.x + box.width - 30, box.y + 120);
  await page.mouse.down();
  await page.mouse.move(box.x + 40, box.y + 130, { steps: 6 });
  await page.mouse.up();
  await expect(page.locator(".ph-count")).toHaveText("2/3");
  await expect(page.locator(".ph-title")).toHaveText("logger_flush ignores -2");
  await page.getByRole("button", { name: "Previous flow" }).click();
  await expect(page.locator(".ph-count")).toHaveText("1/3");

  // a step expands to its code with annotations
  await steps.nth(2).locator(".ph-head").click();
  await expect(page.locator(".ph-step.open .bd-ann").first()).toContainText("writes Uart::errors through alias");

  // ⤢ opens the whole file in the Files tab at the function
  await page.locator(".ph-step.open").getByRole("button", { name: "Open uart_send in Files" }).click();
  await expect(tab(page, "Files")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator('.bd-viewer .fsec[data-path="//fixture/driver/uart.c"]')).toBeVisible();
  await expect(page.locator(".bd-viewer .bd-ln.focus")).toContainText("int uart_send");
  await page.locator(".bd-viewer").getByRole("button", { name: "Close all" }).click();
  await expect(page.locator(".ph-pick")).toContainText("uart.c");
  await expect(page.locator(".ph-pick")).toContainText("logger.c");                 // files with side effects

  // Summary: the change panel, with side-effect files that open in Files
  await tab(page, "Summary").click();
  const summary = page.locator(".bd-about");
  await expect(summary.getByText("Files with side effects")).toBeVisible();
  await summary.locator(".fx-fn", { hasText: "logger_flush" }).click();
  await expect(tab(page, "Files")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator('.bd-viewer .fsec[data-path="//fixture/service/logger.c"]')).toBeVisible();

  // Map shows the graph; the review menu holds the other pages
  await tab(page, "Map").click();
  await expect(page.locator(".bd-node").first()).toBeVisible();
  await page.getByRole("button", { name: "Review menu" }).click();
  await expect(page.locator(".ph-menu").getByRole("link", { name: /Findings/ })).toBeVisible();
  await expect(page.locator(".ph-menu .theme-switch")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});

test("the phone tab is remembered for the review", async ({ page }) => {
  await startReview(page);
  await tab(page, "Summary").click();
  await page.reload();
  await expect(tab(page, "Summary")).toHaveAttribute("aria-selected", "true");
});

test("phone map: pinch to zoom, tap a node for its code, long-press to move it", async ({ page }) => {
  await startReview(page);
  await tab(page, "Map").click();
  const node = page.locator(".bd-node.chg", { hasText: "uart_send" });
  await expect(node).toBeVisible();
  const cdp = await page.context().newCDPSession(page);
  const touch = (type: string, pts: [number, number][]) =>
    cdp.send("Input.dispatchTouchEvent", { type, touchPoints: pts.map(([x, y], id) => ({ x, y, id })) });
  const centre = async () => { const b = (await node.boundingBox())!; return [b.x + b.width / 2, b.y + b.height / 2, b.width] as const; };

  // pinch out around the node: it grows and stays under the fingers
  const [x0, y0, w0] = await centre();
  await touch("touchStart", [[x0 - 30, y0], [x0 + 30, y0]]);
  for (let k = 1; k <= 6; k++) await touch("touchMove", [[x0 - 30 - k * 12, y0], [x0 + 30 + k * 12, y0]]);
  await touch("touchEnd", []);
  const [x1, y1, w1] = await centre();
  expect(w1).toBeGreaterThan(w0 * 1.5);
  expect(Math.hypot(x1 - x0, y1 - y0)).toBeLessThan(40);

  // tap: the node's code opens in a sheet
  await node.tap();
  const sheet = page.locator(".ph-sheet");
  await expect(sheet.locator(".bd-ann").first()).toContainText("through alias");
  await expect(sheet.locator("textarea")).toHaveCount(0);                          // the tap's click must not land in the sheet
  await sheet.getByRole("button", { name: "Close code" }).click();
  await expect(sheet).toHaveCount(0);

  // long-press, then drag: the node moves; a plain drag pans instead
  await touch("touchStart", [[x1, y1]]);
  await page.waitForTimeout(600);
  for (let k = 1; k <= 5; k++) await touch("touchMove", [[x1 + k * 14, y1 + k * 10]]);
  await touch("touchEnd", []);
  await expect(node).toHaveClass(/\bmoved\b/);

  // the floating pill picks flows
  await page.getByLabel("Flow").selectOption({ label: "2 · logger_flush ignores -2" });
  await expect(page.locator(".bd-node.onflow", { hasText: "logger_flush" })).toBeVisible();
});

test("a tap's late click does not land in the code sheet that opened under it", async ({ page }) => {
  await startReview(page);
  await tab(page, "Map").click();
  await page.locator(".bd-node.chg", { hasText: "uart_send" }).tap();
  const sheet = page.locator(".ph-sheet");
  const line = sheet.locator(".bd-ln").first();
  await expect(line).toBeVisible();
  // real phones can deliver the tap's click after the sheet has rendered under the finger: replay it there
  await line.evaluate((el) => {
    const r = el.getBoundingClientRect();
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, clientX: r.x + 30, clientY: r.y + 5 }));
  });
  await expect(sheet.locator("textarea")).toHaveCount(0);
  await line.tap();                                                                 // a real tap in the sheet still comments
  await expect(sheet.locator("textarea")).toHaveCount(1);
});

test("a cited function opens on the phone map with its code", async ({ page }) => {
  await startReview(page);
  const rid = page.url().match(/\/r\/(\d+)/)![1];
  const board = await (await page.request.get(`/api/reviews/${rid}/board`)).json();
  const target = board.nodes.find((n: { label: string }) => n.label === "uart_errors");
  await page.goto(`/r/${rid}?node=${target.id}`);
  await expect(tab(page, "Map")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".ph-sheet .ph-sheet-head")).toContainText("uart_errors");
  const inside = async () => {                                                     // once the eased pan has settled
    const stage = (await page.locator(".bd-stage").boundingBox())!;
    const node = (await page.locator(".bd-node", { hasText: "uart_errors" }).boundingBox())!;
    return node.x >= stage.x && node.x + node.width <= stage.x + stage.width &&
      node.y >= stage.y && node.y + node.height <= stage.y + stage.height;
  };
  await expect.poll(inside).toBe(true);
});
