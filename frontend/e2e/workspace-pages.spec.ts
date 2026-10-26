import { expect, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, openIndex, startReview } from "./helpers";

/** Finding, CL and cluster pages (spec 2026-10-04-review-workspace §3.3–§3.5). */

/** How far each element matching `selector` sits below the sibling before it, in px (one with no sibling before it has no gap). */
const gapsAbove = (page: Page, selector: string) => page.locator(selector).evaluateAll((els) =>
  els.flatMap((el) => {
    const before = el.previousElementSibling;
    return before ? [Math.round((el.getBoundingClientRect().top - before.getBoundingClientRect().bottom) * 10) / 10] : [];
  }));

/** What `selector`'s `at`th match looks like as a heading (spec 2026-10-25-review-ui-redesign §1.3): its case, spacing, weight and
 * size, whether its colour is `--ink`, and its margins. */
const headingLook = (page: Page, selector: string, at = 0) => page.locator(selector).nth(at).evaluate((el) => {
  const cs = getComputedStyle(el), ink = document.createElement("span");
  ink.style.color = "var(--ink)";
  document.body.append(ink);
  const isInk = cs.color === getComputedStyle(ink).color;
  ink.remove();
  return { textTransform: cs.textTransform, letterSpacing: cs.letterSpacing, weight: cs.fontWeight, size: cs.fontSize, ink: isInk,
           above: cs.marginTop, below: cs.marginBottom };
});

/** The §1.3 style: sentence case, `--ink`, weight 650, `size` (16px for an `h2`, 15px for an `h3`, an `h4` and the rail's section
 * button `.ws-sec-t`); a heading in a page's flow also has 20px above and 6px below, which one in a row, a band or a rail
 * (`.rv-head h2`, `.ov-band h3`, `.ws-sec-t`) does not. */
const title = (size: "16px" | "15px", inFlow = false) =>
  ({ textTransform: "none", letterSpacing: "normal", weight: "650", size, ink: true, ...(inFlow && { above: "20px", below: "6px" }) });

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a finding: to its story and back, on the graph, evidence opens the diff at its line", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/f/F4?details=1`);
    await expect(page.locator(".ws-finding h2")).toContainText("uart_send: new return value -2");
    await expect(page.locator(".ws-finding")).toContainText("returns before: 0; after: -2, 0");      // evidence as a list, not a repr
    await expect(page.getByRole("region", { name: "Analysis", exact: true })).toContainText("No analysis: AI is not set up.");
    await page.getByRole("link", { name: /^Go to story S1/ }).first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`${base}/f/F4\\?details=1$`));

    await page.getByRole("link", { name: "Open service/logger.c at line 12" }).first().click();
    await expect(page).toHaveURL(/open=file%3A%2F%2Ffixture%2Fservice%2Flogger\.c%3A12&details=1$/);
    await expect(page.getByRole("complementary", { name: "Code: logger.c" }).locator('[data-n="12"]').first()).toBeVisible();
    await page.goBack();

    await page.getByRole("link", { name: "Show it on the graph" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1\\?view=graph&open=N\\d+$`));
    await expect(page.getByRole("complementary", { name: "Code: uart_send" })).toBeVisible();
    await page.goBack();

    await page.getByRole("link", { name: /^Next finding: F5/ }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/f/F5\\?details=1$`));
    await page.getByRole("button", { name: "mark acknowledged" }).click();
    await expect(page.locator(".ws-finding .ws-badge")).toHaveText("acknowledged");
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("section headings are dark sentence-case titles, not grey capitals", async ({ page }) => {
    const base = await startReview(page), rid = base.split("/")[2];
    // each heading measured on a page that shows it; a failing one is named, and the rest still run
    const see = async (selector: string, want: Record<string, unknown>, { at = 0, as = selector } = {}) => {
      await expect(page.locator(selector).nth(at)).toBeVisible();
      expect.soft(await headingLook(page, selector, at), as).toMatchObject(want);
    };
    await see(".ws-whole h2", title("16px"));
    await page.goto(`${base}/f/F4?details=1`);
    await see(".ws-finding h3", title("15px", true));
    const names = await (await page.request.get(`/api/reviews/${rid}/names`)).json() as Record<string, { label: string }>;
    const send = Object.entries(names).find(([, n]) => n.label === "uart_send")![0];
    await page.goto(`${base}?open=${send}&tab=neighbours`);
    await see(".ws-nb-col h3", title("15px", true));
    await page.getByRole("button", { name: "Tree" }).click();
    await see(".ws-tree-sec h3", title("15px", true));
    await page.goto("/");
    await see(".rv-head h2", title("16px"));
    // a review whose reading has not come keeps the old rail and pages, which carry three more of the headings
    await page.route(`**/api/reviews/${rid}/reading`, (r) =>
      r.fulfill({ status: 404, json: { detail: "this review has no reading: re-run it" } }));
    const story = await (await page.request.get(`/api/reviews/${rid}/stories/S1`)).json();
    await page.route(`**/api/reviews/${rid}/stories/S1`, (r) => r.fulfill({ json: { ...story, reading: null } }));
    await page.goto(base);
    await see(".ws-whole h2", title("16px", true), { at: 1, as: ".ws-whole h2, below another section" });
    await see(".ws-sec-t", title("15px"));
    await page.goto(`${base}/s/S1`);
    await see(".ws-steps h3", title("15px", true));
  });

  test("a fold's arrow is decoration: it carries an empty text alternative, so screen readers skip it", async ({ page }) => {
    await startReview(page);
    const fold = page.getByRole("region", { name: "Build impact", exact: true }), summary = fold.locator("summary");
    await expect(summary).toBeVisible();
    const arrow = () => summary.evaluate((el) => getComputedStyle(el, "::after").content);      // the arrow is the summary's ::after
    expect(await arrow()).toBe('"▸" / ""');
    expect(await fold.ariaSnapshot()).not.toContain("▸");                                       // the accessibility tree holds no text for it
    await summary.click();
    await expect(fold.locator("details")).toHaveAttribute("open", "");
    expect(await arrow()).toBe('"▾" / ""');
    expect(await fold.ariaSnapshot()).not.toContain("▾");
  });

  test("a page's sections keep a gap: the Files index's directories, the old whole-change page's summary box", async ({ page }) => {
    const base = await startReview(page), rid = base.split("/")[2];
    await page.goto(`${base}/i/files`);
    await expect(page.locator(".ix-dir").nth(1)).toBeVisible();                       // two directories or more: there is a gap to measure
    const dirs = await gapsAbove(page, ".ix-dir + .ix-dir");
    expect(dirs.length).toBeGreaterThanOrEqual(1);
    expect.soft(Math.min(...dirs), "the Files index's directories").toBeGreaterThanOrEqual(20);
    // a review whose reading has not come keeps the old page: a section, the stories' summary box, then the map
    await page.route(`**/api/reviews/${rid}/reading`, (r) =>
      r.fulfill({ status: 404, json: { detail: "this review has no reading: re-run it" } }));
    await page.goto(base);
    await expect(page.locator(".ws-whole > .ws-summary")).toBeVisible();
    const blocks = await gapsAbove(page, ".ws-whole > :is(section, .ws-summary)");
    expect(blocks.length).toBeGreaterThanOrEqual(4);
    expect.soft(Math.min(...blocks), "the old whole-change page's sections and summary box").toBeGreaterThanOrEqual(20);
  });

  test("the overview keeps its own spacing: its folds are rows 6px apart, not the 20px of a page's sections", async ({ page }) => {
    await startReview(page);
    const fold = "section:has(> details.ov-fold)";
    await expect(page.locator(`.ov3 > ${fold}`)).toHaveCount(3);                       // Build impact, Coverage, Discussion
    expect(await gapsAbove(page, `.ov3 > ${fold} + ${fold}`)).toEqual([6, 6]);
  });

  test("a header's reach reads as words: counts with their nouns, its layers as a list", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/f/F1?details=1`);
    await expect(page.locator(".ws-finding h2")).toContainText("regs.h: 1 change reaches 4 TUs");
    const finding = page.locator(".ws-finding");
    await expect(finding).toContainText("Changes in include/hal/regs.h affect 4 translation units across 4 layers.");
    await expect(finding).toContainText("included (transitively) by 4 TUs; by layer: ");
    for (const layer of ["L1: hal (1)", "L2: driver (1)", "L3: service (1)", "L4: app (1)"]) await expect(finding).toContainText(layer);
    await expect(finding).not.toContainText("{'");
  });

  test("a side effect is neutral until the AI judges it: no red, and it says it isn't assessed", async ({ page }) => {
    const base = await startReview(page);
    const findings = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/findings`)).json() as { id: string; title: string }[];
    const errors = findings.find((f) => f.title.startsWith("uart_send now writes Uart::errors"))!;
    await page.goto(`${base}/f/${errors.id}`);
    await expect(page.locator(".ws-finding h2 .badge")).toHaveText("info");
    await expect(page.locator(".ws-verdict")).toContainText("Side effect · not yet assessed");
    await page.locator(".ws-where").getByRole("link", { name: /^Go to story/ }).click();
    await page.getByRole("navigation", { name: "Story sections" }).getByRole("link", { name: "Graph" }).click();   // a story's flows are on its graph
    const strip = page.getByRole("region", { name: "Flow" });
    await strip.getByRole("button", { name: "Every flow" }).click();
    await strip.getByRole("menuitemradio", { name: /uart_errors sees a new writer of Uart::errors/ }).click();
    const lands = strip.locator(".ws-flow-lands");
    await expect(lands).toContainText("Side effect lands on uart_errors.");
    await expect(lands).not.toContainText("⚠");
    expect(await lands.locator("b").evaluate((el) => getComputedStyle(el).color))
      .toBe(await lands.evaluate((el) => getComputedStyle(el).color));
  });

  test("a finding without an explanation offers Explain only once the AI is known to be there", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    await page.route(`**/api/reviews/${rid}/ai`, async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.continue(); });
    await page.goto(`${base}/f/F5`);
    const ai = page.getByRole("region", { name: "Analysis", exact: true });
    await expect(ai).toBeVisible();
    for (let i = 0; i < 6; i++) {
      expect(await ai.getByRole("button", { name: /Explain/ }).count()).toBe(0);
      expect(await ai.innerText()).not.toContain("Not written yet");                 // it may never be: say nothing yet
      await page.waitForTimeout(150);
    }
    await expect(ai).toContainText("No analysis: AI is not set up.");
  });

  test("the owner's Swarm buttons say what happened, and a new press clears the last answer", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    let n = 0;
    await page.route(`**/api/reviews/${rid}/cls/102/swarm/refresh`, async (r) => {
      if (n++ === 0) return r.fulfill({ status: 502, json: { detail: "Swarm did not answer" } });
      await new Promise((ok) => setTimeout(ok, 1000));
      return r.fulfill({ json: null });
    });
    await page.goto(`${base}/cl/102`);
    const swarm = page.getByRole("region", { name: "Swarm" });
    await swarm.getByRole("button", { name: "Refresh" }).click();
    await expect(swarm.locator(".banner")).toContainText("Swarm did not answer");
    await swarm.getByRole("button", { name: "Refresh" }).click();
    expect(await swarm.getByText("Swarm did not answer").count()).toBe(0);
    await expect(swarm.locator(".banner")).toHaveText("Swarm state refreshed");
  });

  test("a changelist's description is Markdown: rendered on its page, plain text in the rail and its heading", async ({ page }) => {
    const base = await startReview(page), rid = base.split("/")[2];
    const md = "# uart: **flags** field\n\nWhy:\n\n- adds `flags`\n- see [the spec](https://example.invalid/spec)\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n<img src=x onerror=\"window.__pwned=1\">";
    await page.route(`**/api/reviews/${rid}`, async (r) => {
      const res = await r.fetch(), body = await res.json();
      body.cls = body.cls.map((c: { cl: number; description: string }) => (c.cl === 102 ? { ...c, description: md } : c));
      await r.fulfill({ response: res, json: body });
    });
    await page.goto(`${base}/cl/102`);
    await expect(page.locator(".ws-finding h2")).toHaveText("CL 102 · uart: flags field");
    await page.goto(`${base}/i/cls`);
    // the CL's row, whether the rail lists the CLs (before the reading arrives) or the Index does
    await expect(page.locator("li", { has: page.getByRole("link", { name: "Open CL 102" }) }).first()).toContainText("uart: flags field");
    await page.goto(`${base}/cl/102`);
    const desc = page.locator(".ws-desc");
    await expect(desc.locator("li")).toHaveCount(2);
    await expect(desc.locator("li code")).toHaveText("flags");
    await expect(desc.getByRole("link", { name: "the spec" })).toHaveAttribute("target", "_blank");
    await expect(desc.locator("table td")).toHaveCount(2);
    await expect(desc.locator("img")).toHaveCount(0);                   // raw HTML is never rendered
    expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
    expect(await desc.innerText()).not.toContain("- adds");
  });

  test("a changelist: its Swarm card, its files filtered to it, the stories and findings drawn from it", async ({ page }) => {
    const base = await startReview(page);
    await openIndex(page, "CLs");
    await page.getByRole("link", { name: "Open CL 102" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/cl/102$`));
    await expect(page.locator(".ws-finding h2")).toHaveText("CL 102 · uart: add flags field; hal_write takes unsigned reg");
    await expect(page.getByRole("region", { name: "Swarm" })).toContainText("No Swarm review.");
    await expect(page.getByRole("region", { name: "Swarm" }).getByRole("button", { name: "Refresh" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Stories drawn from this CL" })).toContainText("hal_write");
    await page.getByRole("link", { name: "Open regs.c's diff in CL 102" }).click();
    await expect(page.getByRole("complementary", { name: "Code: regs.c" }).getByLabel("Changelist")).toHaveValue("102");
    await expectNoNodeIds(page);
    await expectNamed(page);
  });
});

test.describe("stories formed by a strong model", () => {
  test.use({ baseURL: "http://127.0.0.1:8795", viewport: { width: 1440, height: 900 } });         // e2e/serve-strong.sh

  test("the global h4 is a dark sentence-case title: a story's \"Also worth checking\" has no rule of its own", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/s/S1`);
    await page.getByRole("navigation", { name: "Story sections" }).getByRole("link", { name: /^Talk/ }).click();
    await expect(page.getByRole("region", { name: "Questions and comments" }).locator(".st-suggested h4")).toHaveText("Also worth checking");
    expect(await headingLook(page, ".st-suggested h4")).toMatchObject(title("15px", true));
  });
});

test.describe("a large change", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });         // e2e/serve-large.sh

  test("a layer band's heading on the map is a dark sentence-case title", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/i/map`);
    await expect(page.locator(".ov-band h3").first()).toBeVisible();
    expect(await headingLook(page, ".ov-band h3")).toMatchObject(title("15px"));
  });
});
