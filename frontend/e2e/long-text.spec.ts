import { expect, type Page, test } from "@playwright/test";
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

test("the story's file tree, the breadcrumb and the outline's story rows stay one line, the whole name on hover", async ({ page }) => {
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
});

test.describe("with an AI", () => {
  test.use({ baseURL: "http://127.0.0.1:8798" });       // e2e/serve-ai.sh: the fake model writes story accounts

  test("a story's account keeps long names inside its box", async ({ page }) => {
    test.setTimeout(180_000);
    await longNames(page);
    const base = await startReview(page);
    await page.goto(`${base}/s/S1`);
    await expect(page.locator(".st-summary .ai-label")).toBeVisible({ timeout: 30_000 });   // the account is in
    await expect(page.getByRole("region", { name: "What it means for the rest" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(await problems(page)).toEqual([]);
  });
});
