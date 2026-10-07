import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

/** Addresses from before the workspace still land (spec 2026-10-04-review-workspace §2.3). */

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the old tabs, the board, a cited node and /w/ go to where those things live now", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    const ss = await (await page.request.get(`/api/reviews/${rid}/stories`)).json();
    const [nid, sid] = Object.entries(ss.node_story as Record<string, string>)[0];
    for (const [old, now] of [["/files", "/i/files"], ["/findings", "/i/checks"], ["/cls", "/i/cls"], ["/overview", "/i/map"],
                              ["/board", "?view=graph"]]) {
      await page.goto(`${base}${old}`);
      await expect(page).toHaveURL(new RegExp(`${base}${now.replace("?", "\\?")}$`));
    }
    await expect(page.locator(".bd-node").first()).toBeVisible();
    await page.goto(`${base}/board?node=${nid}`);
    await expect(page).toHaveURL(new RegExp(`${base}/s/${sid}\\?open=${nid}$`));
    await expect(page.locator(".ws-detail")).toBeVisible();
    await page.goto(`${base}/s/${sid}?tab=graph`);
    await expect(page).toHaveURL(new RegExp(`${base}/s/${sid}\\?view=graph$`));
    await page.goto(`/w/${rid}/s/${sid}?flow=1`);
    await expect(page).toHaveURL(new RegExp(`${base}/s/${sid}\\?flow=1$`));
    // a node in no story, on a review shown as one board: the whole graph with it open
    const board = await (await page.request.get(`/api/reviews/${rid}/board`)).json();
    const ctx = board.nodes.find((n: { id: string; kind: string }) => !ss.node_story[n.id] && n.kind === "function");
    await page.goto(`${base}?node=${ctx.id}`);
    await expect(page).toHaveURL(new RegExp(`${base}\\?view=graph&open=${ctx.id}$`));
    await expect(page.getByRole("complementary", { name: `Code: ${ctx.label}` })).toBeVisible();
  });
});

test.describe("a large change", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });

  test("a cited node outside every story opens the part holding it; one inside a story opens that story", async ({ page }) => {
    const base = await startReview(page, "201 202");
    const rid = base.split("/")[2];
    const ov = await (await page.request.get(`/api/reviews/${rid}/overview`)).json();
    const ss = await (await page.request.get(`/api/reviews/${rid}/stories`)).json();
    const all: { id: string; name: string; nodes: string[] }[] = ov.clusters;
    const told = all.flatMap((c) => c.nodes).find((n) => ss.node_story[n])!;
    await page.goto(`${base}/overview?node=${told}`);
    await expect(page).toHaveURL(new RegExp(`/s/${ss.node_story[told]}\\?open=${told}$`));
    // only the server knows which part holds a node outside every story: serve the stories without this one's
    const part = all.find((c) => c.name === "hal/regs")!, nid = part.nodes[0];
    const { [nid]: _, ...rest } = ss.node_story;
    await page.route(`**/api/reviews/${rid}/stories`, (r) => r.fulfill({ json: { ...ss, node_story: rest } }));
    await page.goto(`${base}?node=${nid}`);
    await expect(page).toHaveURL(new RegExp(`/c/${part.id}\\?open=${nid}$`));
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText(part.name);

    // a reader who leaves before the server answers stays where they went
    await page.route(`**/api/reviews/${rid}/locate**`, async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.continue(); });
    await page.goto(base);
    await expect(page.getByRole("region", { name: "To check" })).toBeVisible();
    await page.evaluate((u) => { history.pushState(null, "", u); dispatchEvent(new PopStateEvent("popstate")); }, `${base}?node=${nid}`);
    await expect(page.locator("main.page")).toContainText("Loading");
    await page.goBack();
    await page.waitForTimeout(2500);
    await expect(page).toHaveURL(new RegExp(`${base}$`));
  });
});
