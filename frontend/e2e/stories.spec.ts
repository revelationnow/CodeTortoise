import { devices, expect, type Page, test } from "@playwright/test";
import { startStories } from "./helpers";

/** Change stories (spec 2026-10-04-change-stories §8): list → story steps → graph → whole graph, citations, ‹ ›. */

const rid = (page: Page) => page.url().match(/\/r\/(\d+)/)![1];

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a review opens on its stories; a story's steps, its graph, the whole graph and back", async ({ page }) => {
    await startStories(page);
    await expect(page.locator(".st-lead")).toContainText("2 behaviour stories.");
    const entries = page.locator(".st-entry");
    await expect(entries).toHaveCount(2);
    await expect(entries.first()).toContainText("uart_send now writes Uart::errors; uart_errors reads it");
    await expect(entries.first().locator(".st-counts")).toHaveText(/2 flows · \d+ findings? · 1 function/);

    await entries.first().click();
    await expect(page).toHaveURL(/\/s\/S1$/);
    await expect(page.locator(".st-head h2")).toContainText("uart_send now writes Uart::errors");
    const send = page.locator(".ph-step").filter({ has: page.locator(".ph-text b", { hasText: /^uart_send$/ }) });
    await expect(send).toHaveCount(1);
    await expect(send.locator(".ph-reason")).toContainText("now writes");                 // the step's note
    await send.locator(".ph-head").click();
    await expect(page.locator(".ph-step.open .bd-code, .ph-step.open .bd-note").first()).toBeVisible();
    await page.getByRole("button", { name: "Next flow" }).click();
    await expect(page.locator(".st-flowbar")).toContainText("flow 2 of 2");
    await expect(page.locator(".st-findings li").first()).toBeVisible();

    await page.getByRole("tab", { name: "Graph" }).click();
    await expect(page).toHaveURL(/\/s\/S1\?tab=graph$/);
    const nodes = page.locator(".bd-node");
    await expect(nodes.first()).toBeVisible();
    expect(await nodes.count()).toBeLessThanOrEqual(12);
    await expect(page.locator(".bd-node.field .fields").first()).toContainText(".errors");   // one node per struct
    await expect(page.locator(".bd-node", { has: page.locator(".lbl", { hasText: /^uart_send$/ }) }).locator(".note"))
      .toHaveText("now writes tx, errors");
    await expect(page.getByRole("button", { name: "4×" })).toHaveCount(0);                     // no lens

    await page.getByRole("link", { name: "Whole graph ›" }).click();
    await expect(page).toHaveURL(new RegExp(`/r/${rid(page)}/board\\?node=N\\d+$`));
    await expect(page.locator(".bd-node").first()).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/s\/S1\?tab=graph$/);
    await page.getByRole("link", { name: "Stories", exact: true }).first().click();
    await expect(page.locator(".st-entry")).toHaveCount(2);
  });

  test("‹ › step between stories and a citation opens the story holding it", async ({ page }) => {
    await startStories(page);
    await page.locator(".st-entry").first().click();
    await page.getByRole("button", { name: "Next story" }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
    await expect(page.locator(".st-head h2")).toContainText("hal_write's signature changed");
    await page.getByRole("button", { name: "Previous story" }).click();
    await expect(page).toHaveURL(/\/s\/S1$/);

    const ss = await (await page.request.get(`/api/reviews/${rid(page)}/stories`)).json();
    const [node, sid] = Object.entries(ss.node_story as Record<string, string>).find(([, s]) => s === "S2")!;
    await page.goto(`/r/${rid(page)}?node=${node}`);
    await expect(page).toHaveURL(new RegExp(`/s/${sid}\\?node=${node}$`));
    await expect(page.locator(".ph-step.open, .st-also li.open")).toHaveCount(1);
  });

  test("a review without stories (run before them) opens on its board", async ({ page }) => {
    await startStories(page);
    await page.route(`**/api/reviews/${rid(page)}/stories`, (r) =>
      r.fulfill({ status: 404, json: { detail: "this review has no stories: re-run it" } }));
    await page.reload();
    await expect(page.getByRole("tablist", { name: "Call flows" })).toBeVisible();
    await expect(page.locator(".st-entry")).toHaveCount(0);
  });

  test("findings are grouped by story", async ({ page }) => {
    await startStories(page);
    await page.getByRole("link", { name: /Findings/ }).first().click();
    await expect(page.locator(".fg .fg-id").first()).toHaveText("S1");
    await expect(page.getByRole("region", { name: /^Findings in uart_send now writes/ })).toBeVisible();
  });

  test("a repeated edit lists its sites by file, hides tests and links its effects", async ({ page }) => {
    await startStories(page);
    const id = rid(page);
    // neither e2e fixture has a repeated edit: this story is served as the API would for one
    const site = (path: string, line: number, test = false, effect: string | null = null) => ({
      path, line, function: test ? "test_free" : "free_it", node: null, before: "git_vector_free(&v);",
      after: "git_vector_dispose(&v);", test, effect, other_edits: null });
    const story = { id: "S3", kind: "mechanical", title: "`git_vector_free` → `git_vector_dispose` at 3 sites in 2 files (1 in tests)",
      summary: "Every changed line in these 2 functions is this one edit.", text_source: "template", risk: null,
      counts: { sites: 3, files: 2, test_sites: 1 }, nodes: [], flows: [], findings: [], board: null,
      sub: ["git_vector_free", "git_vector_dispose"], subs: [], collapsed: false };
    const real = await (await page.request.get(`/api/reviews/${id}/stories`)).json();
    await page.route(`**/api/reviews/${id}/stories`, (r) => r.fulfill({ json: { ...real, stories: [...real.stories, story] } }));
    await page.route(`**/api/reviews/${id}/stories/S3`, (r) => r.fulfill({ json: {
      story, board: { nodes: [], edges: [], flows: [], impacts: [], layers: [], about: real.about ?? { intent: "", intent_source: "template", why: [], cls: [], tree: [], drift: [] }, hidden_nodes: 0 },
      graph: null, functions: [], also_in: [{ node: "N7", label: "busy", story: "S2" }],
      sites: [site("//fixture/driver/uart.c", 12, false, "S1"), site("//fixture/driver/uart.c", 30), site("//fixture/tests/t.c", 4, true)] } }));
    await page.reload();
    await page.locator(".st-entry", { hasText: "git_vector_dispose" }).click();
    await expect(page.locator(".st-entry.compact, .st-sites li")).not.toHaveCount(0);
    await expect(page.locator(".st-sites li")).toHaveCount(3);
    await expect(page.locator(".st-dir h3").first()).toContainText("//fixture/driver");
    await expect(page.locator(".st-sites li").first()).toContainText("free_it · line 12");
    await page.getByLabel(/Hide tests/).check();
    await expect(page.locator(".st-sites li")).toHaveCount(2);
    await page.getByRole("link", { name: "busy (S2)" }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
    await page.goBack();
    await page.getByRole("link", { name: "has an effect ›" }).click();
    await expect(page).toHaveURL(/\/s\/S1$/);
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });
  const tab = (page: Page, name: string) => page.locator(".ph-tabs").getByRole("tab", { name });

  test("the story list first; a story's Steps and Graph tabs; the menu lists the stories", async ({ page }) => {
    await startStories(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await page.locator(".st-entry").first().click();
    await expect(tab(page, "Steps")).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".st-head h2")).toContainText("uart_send now writes Uart::errors");
    await expect(page.locator(".ph-step").first()).toBeVisible();
    await tab(page, "Graph").click();
    await expect(page.locator(".bd-node").first()).toBeVisible();
    expect(await page.locator(".bd-node").count()).toBeLessThanOrEqual(12);
    await page.getByRole("button", { name: "Review menu" }).click();
    const menu = page.locator(".ph-menu");
    await expect(menu.getByRole("link", { name: /^S2 · / })).toBeVisible();
    await menu.getByRole("link", { name: "Boards" }).click();
    await expect(page).toHaveURL(/\/board$/);
    await expect(page.locator(".bd-node, .ph-step").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
