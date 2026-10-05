import { devices, expect, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, flowStripHolds, startReview } from "./helpers";

/** A story in the workspace (spec 2026-10-04-review-workspace §3.2, §2.4). */

const step = (page: Page, label: string) => page.getByRole("list", { name: "Flow steps" }).getByRole("link", { name: `Open ${label}'s code` });
const node = (page: Page, label: string) => page.locator(".bd-node", { has: page.locator(".lbl", { hasText: new RegExp(`^${label}$`) }) });

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("steps open the detail panel and mark the step; flows replace history; findings link to their pages", async ({ page }) => {
    const base = await startReview(page);
    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page.locator(".ws-story-head h2")).toContainText("uart_send can now return -2");
    await expect(page.getByRole("tab", { name: "Steps" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".ws-story-meta .ws-chip")).toHaveText(["CL 101"]);
    await step(page, "uart_send").click();
    await expect(page).toHaveURL(/\/s\/S1\?open=N\d+$/);
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Close uart_send's code" })).toHaveAttribute("aria-current", "true");
    await page.getByRole("link", { name: "Close uart_send's code" }).click();
    await expect(page.locator(".ws-detail")).toHaveCount(0);

    await flowStripHolds(page);
    await page.goBack();                                       // flows replaced the entry: Back undoes the close
    await expect(page.locator(".ws-detail")).toBeVisible();
    await page.goForward();
    await page.getByRole("link", { name: /^Go to finding F1:/ }).first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/f/F1$`));
    await expectNoNodeIds(page);
  });

  test("names in text read as text: the sentence's colour and a faint dotted underline, the accent on hover", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/f/F4`);
    const name = page.locator(".ws-where li .ws-name").first();
    await expect(name).toBeVisible();
    const look = () => name.evaluate((el) => {
      const s = getComputedStyle(el), p = getComputedStyle(el.closest("li")!);
      return { color: s.color, parent: p.color, line: s.textDecorationLine, style: s.textDecorationStyle, border: s.borderBottomStyle };
    });
    const at = await look();
    expect(at.color).toBe(at.parent);
    expect(at).toMatchObject({ line: "underline", style: "dotted", border: "none" });
    await name.hover();
    expect((await look()).color).not.toBe(at.parent);
  });

  test("the graph: a node click opens and closes its code; ‹ › keep their place between stories", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/s/S1`);
    await page.getByRole("tab", { name: "Graph" }).click();
    await expect(page).toHaveURL(/\/s\/S1\?view=graph$/);
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Graph");
    await node(page, "uart_send").click();
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await node(page, "uart_send").click();
    await expect(page.locator(".ws-detail")).toHaveCount(0);
    await flowStripHolds(page);
    await expectNamed(page);

    await page.getByRole("tab", { name: "Steps" }).click();
    await expect(page.getByRole("list", { name: "Flow steps" })).toBeVisible();     // measure in the Steps layout
    const next = page.getByRole("link", { name: /^Next story/ });
    const x = (await next.boundingBox())!.x;
    await next.click();
    await expect(page).toHaveURL(/\/s\/S2$/);
    await expect(page.locator(".ws-story-head h2")).toContainText("hal_write");
    expect((await page.getByRole("link", { name: /^Next story/ }).boundingBox())!.x).toBe(x);
  });

  test("leaving a story for a CL and coming back returns to the same view, flow and open node", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/s/S1?view=graph`);
    await page.getByRole("button", { name: "Next flow" }).click();
    await node(page, "uart_send").click();
    await expect(page).toHaveURL(/view=graph&flow=2&open=N\d+$/);
    const there = page.url();
    await page.locator(".ws-rail").getByRole("link", { name: "Open CL 101" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/cl/101$`));
    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page).toHaveURL(there);
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await expect(page.locator(".ws-flow-pos")).toHaveText("flow 2 of 2");
  });

  test("a review without stories (run before them) leaves Stories out of the rail", async ({ page }) => {
    const base = await startReview(page);
    await page.route(`**/api/reviews/${base.split("/")[2]}/stories`, (r) =>
      r.fulfill({ status: 404, json: { detail: "this review has no stories: re-run it" } }));
    await page.reload();
    await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to finding/ }).first()).toBeAttached();
    await expect(page.locator(".ws-rail").getByRole("button", { name: /^Stories/ })).toHaveCount(0);
    await expect(page.getByRole("region", { name: "The map" })).toBeVisible();
  });

  test("a story the server sends without a graph drops the Graph tab and shows its steps", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    const real = await (await page.request.get(`/api/reviews/${rid}/stories/S1`)).json();
    await page.route(`**/api/reviews/${rid}/stories/S1`, (r) => r.fulfill({ json: { ...real, graph: null } }));
    await page.goto(`${base}/s/S1?view=graph`);
    await expect(page.getByRole("list", { name: "Flow steps" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Graph" })).toHaveCount(0);
  });

  test("a repeated edit lists its sites by file, hides tests and links its effects", async ({ page }) => {
    const base = await startReview(page);
    const id = base.split("/")[2];
    // neither e2e fixture has a repeated edit: this story is served as the API would for one
    const site = (path: string | null, line: number, test = false, effect: string | null = null) => ({
      path, line, function: test ? "test_free" : "free_it", node: null, before: "git_vector_free(&v);",
      after: "git_vector_dispose(&v);", test, effect, other_edits: null });
    const story = { id: "S9", kind: "mechanical", title: "`git_vector_free` → `git_vector_dispose` at 3 sites in 2 files (1 in tests)",
      summary: "Every changed line in these 2 functions is this one edit.", text_source: "template", risk: null,
      counts: { sites: 3, files: 2, test_sites: 1 }, nodes: [], flows: [], findings: [], board: null, cls: [101],
      sub: ["git_vector_free", "git_vector_dispose"], subs: [], collapsed: false };
    const real = await (await page.request.get(`/api/reviews/${id}/stories`)).json();
    await page.route(`**/api/reviews/${id}/stories`, (r) => r.fulfill({ json: { ...real, stories: [...real.stories, story] } }));
    await page.route(`**/api/reviews/${id}/stories/S9`, (r) => r.fulfill({ json: {
      story, board: { nodes: [], edges: [], flows: [], impacts: [], layers: [], about: real.about ?? { intent: "", intent_source: "template", why: [], cls: [], tree: [], drift: [] }, hidden_nodes: 0 },
      graph: null, functions: [], also_in: [{ node: "N7", label: "busy", story: "S2" }],
      sites: [site("//fixture/driver/uart.c", 12, false, "S1"), site("//fixture/driver/uart.c", 30), site("//fixture/tests/t.c", 4, true),
              site(null, 7, true)] } }));
    await page.goto(`${base}/s/S9`);
    const sites = page.locator(".ws-sites li");
    await expect(sites).toHaveCount(4);
    const unknown = sites.filter({ hasText: "line 7" });          // a site whose file the server could not name
    await expect(unknown).toContainText("test_free · line 7");
    await expect(unknown.getByRole("link")).toHaveCount(0);
    await page.getByLabel(/Hide tests/).check();
    await expect(sites).toHaveCount(2);
    await expect(page.locator(".ws-dir h3").first()).toContainText("//fixture/driver");
    await expect(sites.first()).toContainText("free_it · line 12");
    await sites.first().getByRole("link", { name: "Open uart.c at line 12" }).click();
    await expect(page.getByRole("complementary", { name: "Code: uart.c" })).toBeVisible();
    await page.locator(".ws-mech").getByRole("link", { name: "Go to story S2" }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
    await page.goBack();
    await sites.filter({ hasText: "line 12" }).getByRole("link", { name: "Go to story S1" }).click();
    await expect(page).toHaveURL(/\/s\/S1$/);
  });
});

test.describe("a story loading", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the Steps | Graph switch and ‹ › are in place from the first paint, on the graph's layout", async ({ page }) => {
    const base = await startReview(page);
    await page.route(/\/api\/reviews\/\d+\/stories\/S1$/, async (route) => {
      const res = await route.fetch();
      await new Promise((r) => setTimeout(r, 3000));
      await route.fulfill({ response: res });
    });
    await page.goto(`${base}/s/S1?view=graph`);
    await expect(page.getByText("Loading S1…")).toBeVisible();
    const graph = page.getByRole("tab", { name: "Graph" }), next = page.getByRole("link", { name: /^Next story/ });
    expect(await graph.getAttribute("aria-selected", { timeout: 500 })).toBe("true");     // there while it loads, not after
    const before = [(await graph.boundingBox())!, (await next.boundingBox())!];
    await expect(page.getByText("Loading S1…")).toBeVisible();
    await expect(page.locator(".ws-graph .bd-node").first()).toBeVisible();
    await expect(page.getByText("Loading S1…")).toHaveCount(0);
    expect([(await graph.boundingBox())!, (await next.boundingBox())!]).toEqual(before);
  });
});

test.describe("re-run", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("after Re-run a story page shows the new run's story, not the one cached from before", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/s/S1`);
    await expect(page.locator(".ws-story-head h2")).toContainText("uart_send can now return -2");
    await page.route(/\/api\/reviews\/\d+\/stories\/S1$/, async (route) => {   // any fetch from here on is the new run's
      const res = await route.fetch(), j = await res.json();
      j.story.title = "the new run's S1";
      await route.fulfill({ response: res, json: j });
    });
    await page.getByRole("button", { name: "Re-run" }).click();
    await expect(page.locator(".ws-story-head h2")).toContainText("the new run's S1", { timeout: 40_000 });
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("rail → story → detail sheet, each top bar naming the place", async ({ page }) => {
    await startReview(page);
    await page.getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page.locator(".ws-phonebar")).toContainText("‹ Stories");
    await step(page, "uart_send").click();
    const bar = page.locator(".ws-detail .ws-phonebar");
    await expect(bar).toContainText("‹ S1");
    await expect(bar).toContainText("uart_send");
    await bar.getByRole("link", { name: "Close the code" }).click();
    await expect(page.locator(".ws-centre .ws-phonebar")).toContainText("‹ Stories");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});

test.describe("a story's flows on its graph", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });

  test("flow=N is the same flow on Steps and Graph; a flow too long to draw says so and links to Steps", async ({ page }) => {
    const base = await startReview(page, "201 202");
    const rid = base.split("/")[2];
    const get = async (url: string) => (await page.request.get(`/api/reviews/${rid}/${url}`)).json();
    let sid = "";
    for (const st of (await get("stories")).stories as { id: string; kind: string }[]) {
      const d = st.kind === "behaviour" ? await get(`stories/${st.id}`) : null;
      if (d?.graph?.flows.length >= 3) { sid = st.id; break; }
    }
    expect(sid).not.toBe("");
    await page.route(`**/api/reviews/${rid}/stories/${sid}`, async (route) => {     // the first flow is too long to draw
      const res = await route.fetch(), j = await res.json();
      j.graph.flows = j.graph.flows.slice(1);
      await route.fulfill({ response: res, json: j });
    });
    await page.goto(`${base}/s/${sid}?flow=2`);
    const strip = page.getByRole("region", { name: "Flow" }), title = strip.locator(".ws-flow-title");
    await expect(title).not.toHaveText("");
    const second = await title.innerText(), of = await strip.locator(".ws-flow-pos").innerText();
    await page.getByRole("tab", { name: "Graph" }).click();
    await expect(page).toHaveURL(/view=graph&flow=2$/);
    await expect(page.locator(".ws-graph .bd-node").first()).toBeVisible();
    await expect(title).toHaveText(second);
    await expect(strip.locator(".ws-flow-pos")).toHaveText(of);
    await strip.getByRole("button", { name: "Previous flow" }).click();
    await expect(page).toHaveURL(/view=graph&flow=1$/);
    await expect(strip).toContainText("This flow is too long to draw here");
    await strip.getByRole("link", { name: "See it in Steps" }).click();
    await expect(page).toHaveURL(new RegExp(`/s/${sid}\\?flow=1$`));
    await expect(page.getByRole("tab", { name: "Steps" })).toHaveAttribute("aria-selected", "true");
  });
});
