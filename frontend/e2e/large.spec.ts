import { expect, type Locator, type Page, test } from "@playwright/test";
import { login } from "./helpers";

const LARGE = "http://127.0.0.1:8796";      // e2e/serve-large.sh: the generated fixture, CLs 201+202

/** Review the large fixture's CLs and wait for the overview. */
async function startLarge(page: Page) {
  await login(page);
  await page.getByLabel("Changelists (shelved or submitted)").fill("201 202");
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.locator(".ov-block").first()).toBeVisible({ timeout: 60_000 });
}

/** Press and release on a badge or link inside a node. In Whole graph, open cards and the toolbar can sit over small
 * badges and the lens keeps nodes moving, so a pointer click waits forever; the canvas acts on pointerdown/up. */
async function tap(target: Locator) {
  await target.dispatchEvent("pointerdown", { bubbles: true, pointerId: 1, button: 0 });
  await target.dispatchEvent("pointerup", { bubbles: true, pointerId: 1, button: 0 });
}

const block = (page: Page, name: string) => page.locator(".ov-block", { has: page.locator(".nm", { hasText: new RegExp(`^${name}`) }) });

test.describe("a large change", () => {
  test.use({ baseURL: LARGE, viewport: { width: 1440, height: 900 } });

  test("the overview shows each cluster in its layer, with risk, counts and links", async ({ page }) => {
    await startLarge(page);
    await expect(page.locator(".ov-block")).toHaveCount(7);
    await expect(page.getByText("13 files · 7 clusters")).toBeVisible();
    const uart = block(page, "drv/uart");
    await expect(uart.locator(".ct")).toContainText("5 changed");
    await expect(uart.locator(".ln").first()).toContainText(/calls/);
    await expect(page.getByRole("region", { name: "Layer drv" })).toContainText("drv/dma");
    await uart.click();                                                   // select: linked clusters are outlined
    await expect(uart).toHaveClass(/sel/);
    await expect(block(page, "hal/regs")).toHaveClass(/lit/);
    await expect(block(page, "app/telemetry")).not.toHaveClass(/lit/);
    // each file in the change's tree names its cluster
    await expect(page.locator(".bd-about .tree .file", { hasText: "regs_a.c" }).locator(".ctag")).toHaveText("hal/regs");
  });

  test("a cluster's board: breadcrumb, ‹ › and back to the overview", async ({ page }) => {
    await startLarge(page);
    await block(page, "hal/regs").getByRole("button", { name: /^Open/ }).click();
    await expect(page).toHaveURL(/\/c\/C\d+$/);
    await expect(page.locator(".bd-crumb")).toContainText("Overview › hal/regs");
    await expect(page.locator(".bd-head .bd-pill", { hasText: /^\d+ flows · \d+ findings?$/ })).toBeVisible();   // this cluster's
    expect(await page.locator(".bd-node").count()).toBeLessThanOrEqual(30);
    const here = page.url();
    await page.getByRole("button", { name: "Next cluster" }).click();
    await expect(page).not.toHaveURL(here);
    await page.getByRole("button", { name: "Previous cluster" }).click();
    await expect(page).toHaveURL(here);
    await page.locator(".bd-crumb").getByRole("link", { name: "Overview" }).click();
    await expect(page.locator(".ov-block")).toHaveCount(7);
  });

  test("a bad expansion in the address says so and Reset clears it", async ({ page }) => {
    await startLarge(page);
    await block(page, "hal/regs").getByRole("button", { name: /^Open/ }).click();
    await expect(page).toHaveURL(/\/c\/C\d+$/);
    await page.goto(`${page.url()}?x=N1:sideways`);
    const banner = page.locator(".banner.warn", { hasText: "bad expansion" });
    await expect(banner).toBeVisible();
    await banner.getByRole("button", { name: "Reset" }).click();
    await expect(page.locator(".bd-crumb")).toContainText("hal/regs");
    await expect(page).not.toHaveURL(/x=/);
  });

  test("a visitor opens its own cluster's board, focused on it", async ({ page }) => {
    await startLarge(page);
    await block(page, "hal/regs").getByRole("button", { name: /^Open/ }).click();
    await page.getByRole("button", { name: "Whole graph" }).click();
    await expect(page.locator(".bd-node.visitor").first()).toBeVisible();
    const visitor = page.locator(".bd-node.visitor").first();
    const label = (await visitor.locator(".lbl").textContent())!;
    await tap(visitor.locator(".bd-home"));
    await expect(page).toHaveURL(/\/c\/C\d+\?node=N\d+/);
    await expect(page.locator(".bd-crumb")).not.toContainText("hal/regs");
    await expect(page.locator(".bd-card .hd b", { hasText: new RegExp(`^${label}$`) })).toBeVisible();
  });

  test("+N callers adds them past the budget, and Reset takes them away", async ({ page }) => {
    await startLarge(page);
    await block(page, "hal/regs").getByRole("button", { name: /^Open/ }).click();
    await page.getByRole("button", { name: "Whole graph" }).click();
    const before = await page.locator(".bd-node").count();
    await expect(page.locator(".bd-more-nb [data-act='callers']").first()).toBeVisible();
    const more = page.locator(".bd-more-nb [data-act='callers']").first();
    const n = Number((await more.textContent())!.match(/\d+/)![0]);
    await tap(more);
    await expect(page.locator(".bd-node")).toHaveCount(before + Math.min(n, 10));
    await expect(page).toHaveURL(/x=N\d+(%3A|:)callers/);
    const reset = page.getByRole("button", { name: /nodes · Reset/ });
    await expect(reset).toHaveText(`${before + Math.min(n, 10)} nodes · Reset`);
    const nodes = page.locator(".bd-node:has(.bd-go)");
    for (let i = 0; i < 3; i++) await tap(nodes.nth(i).locator(".lbl"));        // three or more open code cards
    await expect.poll(() => page.locator(".bd-card").count()).toBeGreaterThanOrEqual(3);
    const r = (await reset.boundingBox())!;
    const onTop = await page.evaluate(({ x, y }) => {                           // the newest card dragged over the toolbar
      const cards = [...document.querySelectorAll<HTMLElement>(".bd-card")];
      const top = cards.reduce((a, b) => (Number(getComputedStyle(b).zIndex) > Number(getComputedStyle(a).zIndex) ? b : a));
      const stage = top.offsetParent!.getBoundingClientRect();
      Object.assign(top.style, { left: `${x - stage.left - 20}px`, top: `${y - stage.top - 20}px`, transform: "none" });
      return document.elementFromPoint(x, y)?.closest("button")?.textContent ?? null;
    }, { x: r.x + r.width / 2, y: r.y + r.height / 2 });
    expect(onTop).toMatch(/nodes · Reset/);
    await reset.click();
    await expect(page.locator(".bd-node")).toHaveCount(before);
    await expect(reset).toHaveCount(0);
  });

  test("a citation opens the cluster that holds the node", async ({ page }) => {
    await startLarge(page);
    const rid = page.url().match(/\/r\/(\d+)/)![1];
    const ov = await (await page.request.get(`/api/reviews/${rid}/overview`)).json();
    const regs = ov.clusters.find((c: { name: string }) => c.name === "hal/regs");
    await page.goto(`/r/${rid}?node=${regs.nodes[0]}`);
    await expect(page).toHaveURL(new RegExp(`/c/${regs.id}\\?node=${regs.nodes[0]}`));
    await expect(page.locator(".bd-crumb")).toContainText("hal/regs");
  });

  test("a node asked for on a board that doesn't show it opens the board that does", async ({ page }) => {
    await startLarge(page);
    const rid = page.url().match(/\/r\/(\d+)/)![1];
    const ov = await (await page.request.get(`/api/reviews/${rid}/overview`)).json();
    const regs = ov.clusters.find((c: { name: string }) => c.name === "hal/regs");
    const shown = new Set((await (await page.request.get(`/api/reviews/${rid}/board?cluster=${regs.id}`)).json())
      .nodes.map((n: { id: string }) => n.id));
    const other = ov.clusters.find((c: { id: string; nodes: string[] }) => c.id !== regs.id && c.nodes.some((n) => !shown.has(n)));
    const node = other.nodes.find((n: string) => !shown.has(n));
    await page.goto(`/r/${rid}/c/${regs.id}?node=${node}`);
    await expect(page).toHaveURL(new RegExp(`/c/${other.id}\\?node=${node}$`));
    await expect(page.locator(".bd-crumb")).toContainText(other.name);
  });

  test("findings are grouped by cluster", async ({ page }) => {
    await startLarge(page);
    await page.getByRole("link", { name: /Findings/ }).click();
    await expect(page.getByRole("region", { name: "Findings in hal/regs" })).toBeVisible();
    const of = page.getByLabel("Findings of");
    await of.selectOption({ label: (await of.locator("option", { hasText: "hal/regs" }).textContent())! });
    await expect(page.locator(".fg")).toHaveCount(1);
  });
});

test.describe("a large change on a phone", () => {
  test.use({ baseURL: LARGE, viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("the overview stacks the clusters; opening one shows its phone board", async ({ page }) => {
    await startLarge(page);
    const first = page.locator(".ov-block").first(), second = page.locator(".ov-block").nth(1);
    const a = (await first.boundingBox())!, b = (await second.boundingBox())!;
    expect(b.y).toBeGreaterThan(a.y + a.height - 1);                      // stacked, not side by side
    expect(a.width).toBeGreaterThan(300);
    await first.getByRole("button", { name: /^Open/ }).click();
    await expect(page.locator(".ph-tabs")).toBeVisible();
    await expect(page.locator(".bd-crumb .pos")).toBeVisible();
    await expect(page.locator(".bd-crumb .pos")).toHaveText(/^C\d+ of 7$/);
    await expect(page.getByRole("button", { name: "Next cluster" })).toBeVisible();
    await page.getByRole("button", { name: "Review menu" }).click();
    await expect(page.locator(".ph-menu").getByRole("link", { name: "Overview" })).toBeVisible();
  });
});
