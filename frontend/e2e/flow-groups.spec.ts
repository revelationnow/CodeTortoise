import { devices, expect, test, type APIResponse, type Locator, type Page, type Route } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startReview } from "./helpers";

const FOUR = "101 102 103 104";

/** A reading stored before checks named the changed function that raised them (Review Focus 1). */
async function withoutRelated(page: Page) {
  const strip = async (route: Route) => {
    let res: APIResponse, j: any;
    try { res = await route.fetch(); j = await res.json(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    const r = j.reading ?? j;
    for (const k of [...r?.checks ?? [], ...r?.cleared ?? []]) delete k.related;
    await route.fulfill({ response: res, json: j });
  };
  await page.route("**/api/reviews/*/reading", strip);
  await page.route("**/api/reviews/*/stories/*", strip);
}

/** Each element's attribute `name`, in order. */
const labels = (l: Locator, name = "aria-label") => l.evaluateAll((els, a) => els.map((e) => e.getAttribute(a)), name);

test.describe("the Flows tab", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("flows come in groups by what changed, a line each; a row opens in place and its box marks its places fine", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const groups = page.locator("section.fl-group");
    await expect(groups).toHaveCount(2);
    expect(await labels(groups)).toEqual(["uart_send returns new values", "Uart::errors gets a new writer: uart_send"]);
    await expect(groups.locator(".fl-line")).toHaveText(["called by logger_flush · 1 flow · 1 open", "read by uart_errors · 1 flow · 1 open"]);
    await expect(groups.nth(0).locator(":scope > .st-chips .st-chip"))
      .toHaveText(["logger_flush ignores the result of uart_send, which can now return -2"]);
    await expect(groups.nth(1).locator(":scope > .st-chips .st-chip")).toHaveText(["uart_errors reads Uart::errors, which uart_send now writes"]);
    const toggles = page.locator(".fl-toggle");
    expect(await labels(toggles)).toEqual(["Flow 1: logger_flush ignores -2",
                                           "Flow 2: uart_errors sees a new writer of Uart::errors · via uart_send"]);
    expect(await labels(toggles, "aria-expanded")).toEqual(["false", "false"]);
    await toggles.nth(0).click();
    await page.getByRole("region", { name: /^Flow 1: / }).getByRole("button", { name: "Next flow ›" }).click();
    await expect(toggles.nth(0)).toHaveAttribute("aria-expanded", "false");
    await expect(toggles.nth(1)).toHaveAttribute("aria-expanded", "true");
    const card = page.getByRole("region", { name: /^Flow 2: / });
    await expect(card.locator(".fl-path")).toContainText("uart_send → Uart::errors → uart_errors");
    await expect(card.locator(".fl-path mark")).toHaveText("Uart::errors");
    await expect(card.locator(".fl-check")).toHaveText("Check whether uart_errors assumes Uart::errors only changes the way it did before");
    await card.getByRole("button", { name: "Looks fine" }).click();
    const tick = page.getByRole("checkbox", { name: "Looks fine: uart_errors sees a new writer of Uart::errors · via uart_send" });
    await expect(tick).toBeChecked();
    await expect(groups.nth(1).locator(".fl-line")).toHaveText("read by uart_errors · 1 flow");
    await expect(groups.nth(1).locator(".st-chip.done")).toHaveCount(1);             // its one place was the check's only place
    await tick.click();                                                              // unticking reopens it
    await expect(tick).not.toBeChecked();
    await expect(card.getByRole("button", { name: "Looks fine" })).toBeVisible();
    await page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" }).click();
    await expect(groups.nth(0).locator(".fl-line")).toHaveText("called by logger_flush · 1 flow");
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("a reading stored before checks named their change shows no tick box and keeps every chip (Review Focus 1)", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await withoutRelated(page);
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const groups = page.locator("section.fl-group");
    await expect(page.locator(".fl-row")).toHaveCount(2);
    await expect(page.locator(".fl-tick")).toHaveCount(0);
    await expect(groups.locator(".fl-line")).toHaveText(["called by logger_flush · 1 flow", "read by uart_errors · 1 flow"]);
    await expect(groups.nth(0).locator(":scope > .st-chips .st-chip"))
      .toHaveText(["logger_flush ignores the result of uart_send, which can now return -2"]);
    await expect(groups.nth(1).locator(":scope > .st-chips .st-chip")).toHaveText(["uart_errors reads Uart::errors, which uart_send now writes"]);
    await page.locator(".fl-toggle").first().click();
    const card = page.getByRole("region", { name: /^Flow 1: / });
    await expect(card.locator(".st-chip")).toHaveText(["logger_flush ignores the result of uart_send, which can now return -2",
      "uart_errors reads Uart::errors, which uart_send now writes"]);              // a flow without places shows its causes
    await expect(card.getByRole("button", { name: "Looks fine" })).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});

test.describe("a story with many flows", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });

  test("each group shows eight rows until Show N more; a flow=N address unfolds its group and opens its row", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const groups = page.locator("section.fl-group");
    await expect(groups).toHaveCount(6);                                             // 140 flows
    await expect(groups.first()).toHaveAttribute("aria-label", "TelemDev::errors gets new writers: telem_a1, telem_a2, telem_a3 and 2 more");
    await expect(groups.first().locator(".fl-line")).toHaveText("read by telem_d1, telem_d2, telem_d3 and 2 more · 25 flows · 25 open");
    await expect(page.locator(".fl-row")).toHaveCount(48);
    expect((await page.locator(".fl-more").allTextContents()).sort())
      .toEqual(["Show 17 more", "Show 17 more", "Show 17 more", "Show 17 more", "Show 17 more", "Show 7 more"]);
    await groups.first().getByRole("button", { name: "Show 17 more" }).click();
    await expect(groups.first().locator(".fl-row")).toHaveCount(25);
    await expect(page.locator(".fl-more")).toHaveCount(5);
    await expect(page.getByRole("region", { name: "Also in this story" })
      .getByRole("link", { name: "Open check: 26 functions no test calls" })).toBeVisible();
    await page.goto(`${base}/s/S1?flow=60`);                                         // the tenth row of UartDev::errors: folded
    await expect(page.getByRole("region", { name: /^UartDev::errors gets new writers: / }).locator(".fl-row")).toHaveCount(25);
    await expect(page.locator("#flow-60 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("region", { name: /^Flow 60: / })).toBeInViewport();
    await expectNoNodeIds(page);
  });

  test("a row among a group's first eight opens in place and leaves the group folded", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const first = page.locator("section.fl-group").first(), toggles = first.locator(".fl-toggle");
    await expect(first.locator(".fl-row")).toHaveCount(8);
    for (const i of [2, 7]) {                                                        // the third row, and the eighth: the last showing
      await toggles.nth(i).click();
      await expect(toggles.nth(i)).toHaveAttribute("aria-expanded", "true");
      await expect(first.locator(".fl-row")).toHaveCount(8);
      await expect(first.locator(".fl-more")).toHaveText("Show 17 more");
      await toggles.nth(i).click();                                                  // and closing it changes nothing either
      await expect(toggles.nth(i)).toHaveAttribute("aria-expanded", "false");
      await expect(first.locator(".fl-row")).toHaveCount(8);
      await expect(first.locator(".fl-more")).toHaveText("Show 17 more");
    }
  });

  test("Next flow › from the last row showing opens the first hidden one, which unfolds its group for good", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const first = page.locator("section.fl-group").first(), toggles = first.locator(".fl-toggle");
    await toggles.nth(7).click();                                                    // the eighth row, the last showing
    await first.getByRole("region", { name: /^Flow \d+: / }).getByRole("button", { name: "Next flow ›" }).click();
    await expect(first.locator(".fl-row")).toHaveCount(25);                          // the ninth was hidden: its group unfolds
    await expect(first.locator(".fl-more")).toHaveCount(0);
    await expect(toggles.nth(8)).toHaveAttribute("aria-expanded", "true");
    await toggles.nth(8).click();                                                    // closing it does not fold the group away
    await expect(toggles.nth(8)).toHaveAttribute("aria-expanded", "false");
    await expect(first.locator(".fl-row")).toHaveCount(25);
    await expect(first.locator(".fl-more")).toHaveCount(0);
  });

  test("a flow=N address beyond the fold unfolds its group, and closing the row leaves it unfolded", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1?flow=60`);
    const group = page.getByRole("region", { name: /^UartDev::errors gets new writers: / });
    await expect(group.locator(".fl-row")).toHaveCount(25);
    await expect(page.locator("#flow-60 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await page.locator("#flow-60 .fl-toggle").click();
    await expect(page.locator("#flow-60 .fl-toggle")).toHaveAttribute("aria-expanded", "false");
    await expect(group.locator(".fl-row")).toHaveCount(25);
    await expect(group.locator(".fl-more")).toHaveCount(0);
  });
});

test.describe("the Flows tab on a phone", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("rows stay one line and nothing scrolls sideways, closed or open", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    await expect(page.locator(".fl-row").first()).toBeVisible();
    const wrapped = () => page.locator(".fl-one").evaluateAll((els) => els.filter((e) =>
      e.getBoundingClientRect().height > 1.5 * parseFloat(getComputedStyle(e).lineHeight)).length);
    // The page scrolls inside `.ws-page`, never the document (`main` and the centre clip), so that is what to measure; and a
    // row is readable only when its button sits inside it and its sentence has room (`.fl-one` is nowrap: it can't wrap, it can vanish).
    const sideways = () => page.locator(".ws-page").evaluate((e) => e.scrollWidth - e.clientWidth);
    const unreadable = () => page.locator(".fl-row").evaluateAll((rows) => rows.filter((r) => {
      const b = r.getBoundingClientRect(), t = r.querySelector(".fl-toggle")!.getBoundingClientRect(), o = r.querySelector(".fl-one")!.getBoundingClientRect();
      return t.right > b.right + 1 || o.width < 40;
    }).length);
    await expect(page.getByRole("region", { name: "Also in this story" })).toBeVisible();   // its chips are on this page
    expect(await wrapped()).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    expect(await unreadable()).toBe(0);
    expect(await sideways()).toBeLessThanOrEqual(0);
    await page.locator(".fl-toggle").first().click();
    await expect(page.getByRole("region", { name: /^Flow 1: / })).toBeVisible();
    expect(await wrapped()).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    expect(await unreadable()).toBe(0);
    expect(await sideways()).toBeLessThanOrEqual(0);
  });
});
