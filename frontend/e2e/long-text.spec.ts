import { devices, expect, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

/** Long names (owner feedback 2026-10-10): nothing sticks out of its box; a one-line label that is cut short ends in
 * "…" and shows the whole text on hover. The fixture's names are made long in every answer from the server. */

const FN = "uart_send", LONG_FN = "uart_send_with_retries_and_timeout_handling_for_the_secondary_board_channel";
const DIR = "driver/", LONG_DIR = "driver_support_package_for_the_secondary_board_revision_with_extras/";

async function longNames(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = route.request().url().replaceAll(LONG_DIR, DIR).replaceAll(encodeURIComponent(LONG_DIR), encodeURIComponent(DIR))
      .replaceAll(LONG_FN, FN);
    let res: import("@playwright/test").APIResponse, text: string;
    try { res = await route.fetch({ url }); text = await res.text(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    const type = res.headers()["content-type"] ?? "";
    if (!type.includes("json")) return route.fulfill({ response: res });
    const body = text.replaceAll(FN, LONG_FN).replaceAll(DIR, LONG_DIR)
      .replaceAll(`"${DIR.slice(0, -1)}"`, `"${LONG_DIR.slice(0, -1)}"`);   // a folder named on its own, as the file index has it
    await route.fulfill({ response: res, body });
  });
}

/** Elements in the page whose text runs past their own box, and cut-short labels without the whole text on hover. */
async function problems(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    for (const el of Array.from(document.querySelectorAll<HTMLElement>(".ws-rail *, main *"))) {
      if (el.closest("svg, pre, .bd-code, .bd-resizer, .bd-canvas")) continue;
      if (el.querySelector(":scope > .bd-resizer")) continue;     // a drag edge sits just outside its column by design
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.display === "contents" || el.clientWidth === 0) continue;
      const over = el.scrollWidth > el.clientWidth + 1;
      const text = `${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]} "${(el.textContent ?? "").trim().slice(0, 50)}"`;
      if (over && cs.overflowX === "visible") out.push(`sticks out ${el.scrollWidth - el.clientWidth}px: ${text}`);
      if (over && cs.textOverflow === "ellipsis" && !el.closest("[title]")) out.push(`cut without a hover text: ${text}`);
    }
    return out;
  });
}

test.use({ viewport: { width: 1280, height: 900 } });

test("long names stay inside their boxes on every page, cut-short labels showing the whole name on hover", async ({ page }) => {
  test.setTimeout(240_000);
  await longNames(page);
  const base = await startReview(page);
  const seen: string[] = [];
  for (const path of ["", "/s/S1", "/s/S2", "/cl/101", "/f/F4?details=1", "/i/cls", "/i/files", "/i/findings",
                      "/s/S1?open=finding:F4",
                      "/s/S1?sec=where", "/s/S1?sec=code", "/s/S1?sec=paths", "/s/S1?sec=contracts",
                      "/s/S2?sec=where", "/s/S2?sec=code", "/s/S2?sec=paths", "/s/S2?sec=contracts"]) {
    await page.goto(base + path);
    await expect(page.getByRole("region", { name: "Centre" })).toContainText(/\S/);
    await page.waitForLoadState("networkidle");
    seen.push(...(await problems(page)).map((p) => `${path || "/"}: ${p}`));
  }
  expect(seen).toEqual([]);
  // the outline's Checks, a cause open in the stepper, and every story tab
  await page.goto(`${base}/s/S1`);
  const outline = page.locator("aside.ws-outline");
  await outline.getByRole("button", { name: "Checks" }).click();
  expect(await problems(page), "outline Checks").toEqual([]);
  await outline.locator(".ws-row.cause").first().click();
  await expect(page.locator(".cs")).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(await problems(page), "stepper").toEqual([]);
  const at = new URL(page.url());                                    // the same cause by its address, at its first place
  expect(at.searchParams.get("open")).toMatch(/^cause:c[0-9a-f]{10}$/);
  await page.goto(`${base}/s/S2?open=${at.searchParams.get("open")}&at=1`);
  await expect(page.locator(".cs")).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(await problems(page), "stepper by address").toEqual([]);
  await page.goto(`${base}/s/S1`);
  const tabs = page.getByRole("navigation", { name: "Story sections" });
  for (const name of await tabs.getByRole("link").allInnerTexts()) {
    await tabs.getByRole("link", { name: name.trim() }).click();
    if (name.startsWith("Graph")) continue;                          // the graph has its own checks
    await page.waitForLoadState("networkidle");
    expect(await problems(page), `tab ${name}`).toEqual([]);
  }
  await outline.getByRole("button", { name: "Stories" }).click();
});

/** One-line labels: each listed element is a single line, and its whole text is on hover when it is cut short. */
async function oneLine(page: Page, selector: string): Promise<string[]> {
  return page.locator(selector).evaluateAll((els) => els.flatMap((el) => {
    const lines = Math.round(el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight || "16"));
    const text = (el.textContent ?? "").trim().slice(0, 50);
    const out: string[] = [];
    if (lines > 1) out.push(`${lines} lines: "${text}"`);
    if (el.scrollWidth > el.clientWidth + 1 && !el.closest("[title]")) out.push(`cut without a hover text: "${text}"`);
    return out;
  }));
}

test("the story's file tree, the breadcrumb and the outline's story rows and flow group lines stay one line, the whole name on hover", async ({ page }) => {
  test.setTimeout(240_000);
  await longNames(page);
  const base = await startReview(page);
  await page.goto(`${base}/s/S1?sec=where`);
  await expect(page.getByRole("region", { name: "Where" })).toBeVisible();
  await expect(page.locator(".st-file li > a").first()).toBeVisible();
  expect(await oneLine(page, ".st-file li > a")).toEqual([]);
  const here = page.locator(".ws-crumbs [aria-current]");
  await expect(here).toContainText("…");
  expect(await here.getAttribute("title")).toContain(LONG_FN);
  // a story title in the outline is one line; the row carries the whole title
  const rows = page.locator(".ws-rail .ws-row.story .ws-one");
  await expect(rows.filter({ hasText: "logger_flush" }).first()).toBeVisible();
  expect(await oneLine(page, ".ws-rail .ws-row.story .ws-one")).toEqual([]);
  // and so is a flow group's line under the current story, cut short with its whole text on hover (the long name is the first group's)
  const long = page.locator(".ws-rail .ws-flows a", { hasText: LONG_FN });
  await expect(long).toHaveCount(1);
  expect(await long.locator(".ws-one").evaluate((e) => e.scrollWidth > e.clientWidth)).toBe(true);   // cut short…
  expect(await long.getAttribute("title")).toContain(LONG_FN);                                         // …the whole name on hover
  expect(await oneLine(page, ".ws-rail .ws-flows .ws-one")).toEqual([]);
});

test.describe("with an AI", () => {
  test.use({ baseURL: "http://127.0.0.1:8798" });       // e2e/serve-ai.sh: the fake model writes story accounts

  test("a story's account keeps long names inside its box", async ({ page }) => {
    test.setTimeout(180_000);
    await longNames(page);
    const base = await startReview(page);
    await page.goto(`${base}/s/S1`);
    await expect(page.locator(".st-summary .ai-text")).toBeVisible({ timeout: 30_000 });    // the account is in
    await expect(page.getByRole("region", { name: "What it means for the rest" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(await problems(page)).toEqual([]);
  });
});

/** The first thread's name made very long in every reading the server sends; returns the whole name as a title shows it. */
async function longThreadName(page: Page): Promise<string> {
  await page.route("**/api/reviews/*/reading", async (route) => {
    let res: import("@playwright/test").APIResponse, j: any;
    try { res = await route.fetch(); j = await res.json(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    j.threads[0].name = `\`${LONG_FN}\` in ${LONG_DIR.slice(0, -1)}`;
    await route.fulfill({ response: res, json: j });
  });
  return `${LONG_FN} in ${LONG_DIR.slice(0, -1)}`;
}

test("a long thread name keeps its overview section header and its outline bar on one line, the whole name on hover (review focus 5)", async ({ page }) => {
  const NAME = await longThreadName(page);
  const base = await startReview(page);
  await page.goto(base);
  const head = page.locator(".ov-sec-head").first(), name = page.locator(".ov-sec-name").first();
  await expect(head).toBeVisible();
  expect(await oneLine(page, ".ov-sec-name")).toEqual([]);
  expect(await name.evaluate((e) => e.scrollWidth > e.clientWidth)).toBe(true);         // cut short…
  await expect(name).toHaveAttribute("title", NAME);                                    // …with the whole name on hover
  expect((await head.boundingBox())!.height).toBeLessThan(50);
  const bar = page.locator(".ws-rail .ws-bar > button").first();
  expect(await oneLine(page, ".ws-rail .ws-bar .ws-one")).toEqual([]);
  expect(await bar.locator(".ws-one").evaluate((e) => e.scrollWidth > e.clientWidth)).toBe(true);
  await expect(bar).toHaveAttribute("title", `Thread A: ${NAME}`);
  expect((await page.locator(".ws-rail .ws-bar").first().boundingBox())!.height).toBe(36);
  expect(await problems(page)).toEqual([]);
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("a long thread name keeps its outline bar and its overview header on one line at 390px, the whole name on hover, and nothing scrolls sideways (review focus 5)", async ({ page }) => {
    const NAME = await longThreadName(page);
    await startReview(page);                                                   // a phone opens on the contents: the outline is the page
    await expect(page.locator("main.ws")).toHaveClass(/\bphone\b/);
    expect(page.viewportSize()!.width).toBe(390);
    const bar = page.locator(".ws-rail .ws-bar > button").first();
    await expect(bar).toBeVisible();
    expect(await oneLine(page, ".ws-rail .ws-bar .ws-one")).toEqual([]);
    expect(await bar.locator(".ws-one").evaluate((e) => e.scrollWidth > e.clientWidth)).toBe(true);        // cut short…
    await expect(bar).toHaveAttribute("title", `Thread A: ${NAME}`);                                          // …with the whole name on hover
    expect((await page.locator(".ws-rail .ws-bar").first().boundingBox())!.height).toBe(36);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    expect(await problems(page)).toEqual([]);
    // the overview's section headers (§5.2), the counts wrapped under each name: the same, measured on the page's own scroller
    await page.getByRole("link", { name: "Go to the overview" }).click();
    const names = page.locator(".ov-sec-name");
    await expect(names.first()).toBeVisible();
    expect(await oneLine(page, ".ov-sec-name")).toEqual([]);
    for (const name of await names.all()) {
      expect((await name.boundingBox())!.width, "the name has room").toBeGreaterThan(0);
      expect(await name.evaluate((e) => getComputedStyle(e).textOverflow), "a cut name ends in an ellipsis").toBe("ellipsis");
      await expect(name, "the whole name on hover").toHaveAttribute("title", /\S/);
    }
    expect(await names.first().evaluate((e) => e.scrollWidth > e.clientWidth)).toBe(true);                    // cut short…
    await expect(names.first()).toHaveAttribute("title", NAME);                                               // …with the whole name on hover
    expect(await page.locator(".ws-page").evaluate((e) => e.scrollWidth - e.clientWidth)).toBeLessThanOrEqual(0);
  });
});
