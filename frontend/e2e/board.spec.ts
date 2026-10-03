import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

test.use({ viewport: { width: 1440, height: 900 } });

test("flows, cards, comments, viewer, change panel and layout", async ({ page }) => {
  await startReview(page);
  await expect(page.getByRole("tablist", { name: "Call flows" }).getByRole("tab")).toHaveCount(3);
  await expect(page.locator(".bd-flowinfo .landing")).toContainText("Side effect lands on uart_errors");
  // the landing page's own classes must not leak into the board (its .landing grid once did)
  expect(await page.locator(".bd-flowinfo .landing").evaluate((el) => getComputedStyle(el).display)).toBe("block");

  // select a flow; its summary names where the effect lands
  await page.getByRole("tab", { name: /logger_flush/ }).click();
  await expect(page.locator(".bd-flowinfo .landing")).toContainText("Side effect lands on logger_flush");

  // a step chip toggles that function's card; the card shows the annotation on the call line
  const step = page.locator(".bd-flowinfo .step", { hasText: "logger_flush" });
  const card = page.locator(".bd-card", { hasText: "logger_flush" });
  await step.click();
  await expect(card.locator(".bd-ann.warn")).toContainText("result ignored");
  await step.click();
  await expect(card).toHaveCount(0);

  // comment on a line inside a card
  await step.click();
  await card.locator(".bd-ln", { hasText: "uart_send(lg->uart" }).click();
  await card.getByPlaceholder("Leave a comment…").fill("flush drops -2 silently");
  await card.getByRole("button", { name: "Comment", exact: true }).click();
  await expect(card.getByText("flush drops -2 silently")).toBeVisible();

  // ⤢ on a node opens its file in the viewer, at the function; cards collapse to pills
  await page.getByRole("button", { name: "Close uart_send" }).click();             // the card opened on arrival can cover main
  await page.locator(".bd-node", { hasText: /^main/ }).locator(".bd-go").click();
  const viewer = page.locator(".bd-viewer");
  await expect(viewer.locator('.fsec[data-path="//fixture/app/main.c"]')).toBeVisible();
  await expect(viewer.locator(".bd-ln.focus")).toContainText("int main");
  await expect(card).toHaveClass(/\bmin\b/);

  // stack a second file on top; collapse and expand all
  await page.locator(".bd-flowinfo .step", { hasText: "uart_send" }).locator(".sgo").click();
  await expect(viewer.locator(".fsec").first()).toHaveAttribute("data-path", "//fixture/driver/uart.c");
  await expect(viewer.locator(".fsec")).toHaveCount(2);
  await viewer.getByRole("button", { name: "Collapse all" }).click();
  await expect(viewer.locator(".fsec.collapsed")).toHaveCount(2);
  await viewer.getByRole("button", { name: "Expand all" }).click();
  await expect(viewer.locator(".fsec.collapsed")).toHaveCount(0);
  await viewer.getByRole("button", { name: "Close all" }).click();
  await expect(viewer).toHaveCount(0);
  await expect(card).not.toHaveClass(/\bmin\b/);           // restored exactly

  // the change panel is open beside the board and can be resized from its right edge
  const panel = page.locator(".bd-about");
  await expect(panel.getByText("Files in this change")).toBeVisible();
  const before = (await panel.boundingBox())!;
  const grip = (await panel.locator(".bd-resizer").boundingBox())!;
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2);
  await page.mouse.down();
  await page.mouse.move(grip.x + 100, grip.y + grip.height / 2, { steps: 5 });
  await page.mouse.up();
  expect((await panel.boundingBox())!.width).toBeGreaterThan(before.width + 80);
  await panel.locator(".file", { hasText: "regs.c" }).click();      // opening a file keeps the panel open
  await expect(page.locator(".bd-viewer .fsec")).toHaveCount(1);
  await expect(panel).toBeVisible();
  await page.getByRole("button", { name: "Collapse change summary" }).click();
  await page.locator(".bd-viewer").getByRole("button", { name: "Close all" }).click();
});

test("whole graph: drag a node anywhere in the layers layout, reset; dragging never selects text", async ({ page }) => {
  await startReview(page);
  await page.getByRole("button", { name: "Close uart_send" }).click();   // the card opened on arrival
  await page.getByRole("button", { name: "Whole graph" }).click();
  await expect(page.locator(".bd-flowinfo.whole")).toContainText("Whole graph");
  const node = page.locator(".bd-node", { hasText: /^main/ });
  await page.waitForTimeout(500);                                   // centring animation
  const a = (await node.boundingBox())!;
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(a.x + a.width / 2 + 160, a.y + a.height / 2 + 40, { steps: 8 });
  await page.mouse.up();
  const b = (await node.boundingBox())!;
  expect(b.x).toBeGreaterThan(a.x + 60);
  expect(b.y - a.y).toBeGreaterThan(20);                             // free to leave its band
  await expect(node).toHaveClass(/\bmoved\b/);
  await page.getByRole("button", { name: "Reset layout" }).click();
  await expect(node).not.toHaveClass(/\bmoved\b/);

  // pan across an open card: nothing gets selected
  await page.getByRole("tab", { name: /uart_errors/ }).click();
  await page.locator(".bd-flowinfo .step", { hasText: "uart_errors" }).click();
  const stage = (await page.locator(".bd-stage").boundingBox())!;
  await page.mouse.move(stage.x + stage.width - 30, stage.y + stage.height - 40);
  await page.mouse.down();
  await page.mouse.move(stage.x + 30, stage.y + 120, { steps: 12 });
  await page.mouse.up();
  expect(await page.evaluate(() => window.getSelection()?.toString() ?? "")).toBe("");
});

test("a cited node opens once; closing it sticks when the canvas resizes", async ({ page }) => {
  await startReview(page);
  const rid = page.url().match(/\/r\/(\d+)/)![1];
  const board = await (await page.request.get(`/api/reviews/${rid}/board`)).json();
  const target = board.nodes.find((n: { label: string }) => n.label === "uart_errors");
  await page.goto(`/r/${rid}?node=${target.id}`);
  // by the card's title: other cards' notes can mention uart_errors once their code loads
  const card = page.locator(".bd-card").filter({ has: page.locator(".hd b", { hasText: /^uart_errors$/ }) });
  await expect(card).toBeVisible();
  await page.getByRole("button", { name: "Close uart_errors" }).click();
  await expect(card).toHaveCount(0);
  await page.getByRole("button", { name: "Collapse change summary" }).click();    // widens the canvas
  await expect(page.locator(".bd-about.collapsed")).toBeVisible();
  await page.waitForTimeout(400);
  await expect(card).toHaveCount(0);
});

test("review, layer and function comments from M1 show on the board", async ({ page }) => {
  await startReview(page);
  const rid = page.url().match(/\/r\/(\d+)/)![1];
  const board = await (await page.request.get(`/api/reviews/${rid}/board`)).json();
  const send = board.nodes.find((n: { label: string }) => n.label === "uart_send");
  const post = (body: string, anchor_kind: string, anchor: object) =>
    page.request.post(`/api/reviews/${rid}/comments`, { data: { body, anchor_kind, anchor } });
  await post("overall: please split the CLs", "review", {});
  await post("driver layer looks risky", "chapter", { level: send.layer });
  await post("why -2 and not -EINVAL?", "function", { key: send.key });
  await page.reload();
  await expect(page.locator(".bd-card", { hasText: "uart_send" }).getByText("why -2 and not -EINVAL?")).toBeVisible();
  const panel = page.locator(".bd-about");
  await expect(panel.getByText("overall: please split the CLs")).toBeVisible();
  await expect(panel.getByText("driver layer looks risky")).toBeVisible();
  await panel.getByPlaceholder("Start another thread…").first().fill("agreed");
  await panel.getByRole("button", { name: "Comment" }).first().click();
  await expect(panel.getByText("agreed")).toBeVisible();
});

test("call-depth layout and free 2-D node moves", async ({ page }) => {
  await startReview(page);
  await page.getByRole("button", { name: "Close uart_send" }).click();
  await page.getByRole("button", { name: "Whole graph" }).click();
  await page.getByRole("button", { name: "Call depth" }).click();
  await expect(page.locator(".bd-blabel", { hasText: "depth 0 · entry" })).toBeVisible();
  const node = page.locator(".bd-node", { hasText: /^main/ });
  await page.waitForTimeout(500);                                   // centring animation
  const a = (await node.boundingBox())!;
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(a.x + a.width / 2 + 120, a.y + a.height / 2 + 150, { steps: 10 });
  await page.mouse.up();
  const b = (await node.boundingBox())!;
  expect(b.x - a.x).toBeGreaterThan(60);
  expect(b.y - a.y).toBeGreaterThan(80);                             // left its row
  await expect(node).toHaveClass(/\bmoved\b/);
  await page.getByRole("button", { name: "Layers" }).click();       // moves are kept per layout
  await expect(node).not.toHaveClass(/\bmoved\b/);
  await page.getByRole("button", { name: "Call depth" }).click();
  await expect(node).toHaveClass(/\bmoved\b/);
  await page.getByRole("button", { name: "Reset layout" }).click();
  await expect(node).not.toHaveClass(/\bmoved\b/);
});

test("change panel opens on the left by default, collapses to a bar, and the flow bar resizes", async ({ page }) => {
  await startReview(page);
  const panel = page.locator(".bd-about");
  await expect(panel.getByText("Files in this change")).toBeVisible();
  const stage = (await page.locator(".bd-stage").boundingBox())!;
  expect((await panel.boundingBox())!.x + 10).toBeLessThan(stage.x);              // left of the canvas
  await page.getByRole("button", { name: "Collapse change summary" }).click();
  const bar = page.locator(".bd-about.collapsed");
  await expect(bar).toBeVisible();
  expect((await bar.boundingBox())!.width).toBeLessThan(48);
  await expect(page.getByRole("button", { name: "Show change summary" })).toBeVisible();
  await page.reload();
  await expect(page.locator(".bd-about.collapsed")).toBeVisible();                  // remembered
  await page.getByRole("button", { name: "Show change summary" }).click();
  await expect(panel.getByText("Files in this change")).toBeVisible();

  const flowbar = page.locator(".bd-flowbar");
  const h0 = (await flowbar.boundingBox())!.height;
  const grip = (await flowbar.locator(".bd-resizer.bottom").boundingBox())!;
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2);
  await page.mouse.down();
  await page.mouse.move(grip.x + grip.width / 2, grip.y + grip.height / 2 + 120, { steps: 5 });
  await page.mouse.up();
  expect((await flowbar.boundingBox())!.height).toBeGreaterThan(h0 + 100);
  await expect(page.locator(".bd-flowbar .bd-chip").first()).toBeVisible();
});

test("the change panel lists files with side effects and opens them at the affected line", async ({ page }) => {
  await startReview(page);
  const panel = page.locator(".bd-about");
  const fx = panel.locator(".fx-tree");
  await expect(fx.locator(".fx-file", { hasText: "uart.c" })).toContainText("also changed");
  await expect(fx.locator(".fx-file", { hasText: "logger.c" })).toBeVisible();
  await fx.locator(".fx-fn", { hasText: "logger_flush" }).click();
  const viewer = page.locator(".bd-viewer");
  await expect(viewer.locator('.fsec[data-path="//fixture/service/logger.c"]')).toBeVisible();
  await expect(viewer.locator(".bd-ln.focus")).toContainText("uart_send(lg->uart");
});
