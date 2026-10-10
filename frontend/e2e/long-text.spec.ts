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
    const res = await route.fetch({ url });
    const type = res.headers()["content-type"] ?? "";
    if (!type.includes("json")) return route.fulfill({ response: res });
    const body = (await res.text()).replaceAll(FN, LONG_FN).replaceAll(DIR, LONG_DIR)
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
  await page.evaluate(() => { localStorage.setItem("ct.ws.checkW", "260"); });
  const seen: string[] = [];
  for (const path of ["", "/s/S1", "/s/S2", "/cl/101", "/f/F4?details=1", "/i/cls", "/i/files", "/i/checks"]) {
    await page.goto(base + path);
    await expect(page.getByRole("region", { name: "Centre" })).toContainText(/\S/);
    await page.waitForLoadState("networkidle");
    seen.push(...(await problems(page)).map((p) => `${path || "/"}: ${p}`));
  }
  expect(seen).toEqual([]);
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

test("check locations, the story's file tree and the breadcrumb stay one line, the whole name on hover", async ({ page }) => {
  test.setTimeout(240_000);
  await longNames(page);
  const base = await startReview(page);
  await page.evaluate(() => { localStorage.setItem("ct.ws.checkW", "260"); });
  await page.goto(`${base}/s/S1`);
  await expect(page.getByRole("region", { name: "Centre" })).toContainText(/\S/);
  await expect(page.locator(".ck-place").first()).toBeVisible();
  expect(await oneLine(page, ".ck-place")).toEqual([]);
  expect(await page.locator(".ck-place", { hasText: "driver_support" }).first().getAttribute("title")).toContain(LONG_DIR);
  // the folder gives way first, so the file and line stay in sight
  const file = page.locator(".ck-place", { hasText: "driver_support" }).first().locator(".ck-file");
  await expect(file).toContainText("uart.c:11");
  expect(await file.evaluate((el) => el.parentElement!.getBoundingClientRect().right - el.getBoundingClientRect().left)).toBeGreaterThan(60);
  expect(await oneLine(page, ".st-file li > a")).toEqual([]);
  const here = page.locator(".ws-crumbs [aria-current]");
  await expect(here).toContainText("…");
  expect(await here.getAttribute("title")).toContain(LONG_FN);
  // a story title in the rail stops at three lines; the row carries the whole title
  const title = page.locator(".ws-rail .ws-row-title").filter({ hasText: "logger_flush" }).first();
  const box = await title.evaluate((el) => el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight));
  expect(Math.round(box)).toBeLessThanOrEqual(3);
});
