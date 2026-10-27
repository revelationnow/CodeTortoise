import { devices, expect, test, type APIResponse, type Locator, type Page, type Route } from "@playwright/test";
import { expectNamed, expectNoNodeIds, explainItem, recordSaid, reviewMenu, setShortcuts, sideways, startReview } from "./helpers";

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

/** Story S1 with a second place on its first flow: the review's own flows have one place each, so its Confirm row of `uart_send`
 * becomes a caller row at the first flow's landing (a call that ignores the result and sees the signature change has both). The keys
 * stay the review's, so marking and reopening them reach the server. */
async function withTwoPlaces(page: Page) {
  await page.route("**/api/reviews/*/stories/S1", async (route) => {
    let res: APIResponse, j: any;
    try { res = await route.fetch(); j = await res.json(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    const [flow] = j.board.flows.filter((f: any) => j.story.flows.includes(f.id));
    Object.assign(j.reading.checks.find((k: any) => k.kind === "confirm"), { kind: "caller", node: flow.lands, related: flow.cause });
    await route.fulfill({ response: res, json: j });
  });
}

/** Each element's attribute `name`, in order. */
const labels = (l: Locator, name = "aria-label") => l.evaluateAll((els, a) => els.map((e) => e.getAttribute(a)), name);

/** No mark is on its way from the Flows tab. A tick box is never disabled while one is, and a click on it then is ignored,
 * so a test that ticks again waits for this first. */
const marksDone = (page: Page) => expect(page.locator(".st-flows")).toHaveAttribute("aria-busy", "false");

/** Where a press reaches a tick box (the label around it, else the box itself), and the box. */
const clickable = (tick: Locator) => tick.evaluate((el) => {
  const rect = (r: DOMRect) => ({ x: r.x, y: r.y, width: r.width, height: r.height });
  return { target: rect((el.closest("label") ?? el).getBoundingClientRect()), box: rect(el.getBoundingClientRect()) };
});

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
    await marksDone(page);
    await tick.click();                                                              // unticking reopens it
    await expect(tick).not.toBeChecked();
    await expect(card.getByRole("button", { name: "Looks fine" })).toBeVisible();
    await marksDone(page);
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

  test("J and K move between rows, Enter opens one, F marks its places fine and moves to the next open row", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle");
    await expect(toggles).toHaveCount(2);
    await page.keyboard.press("j");
    await expect(toggles.nth(0)).toBeFocused();
    await page.keyboard.press("j");
    await expect(toggles.nth(1)).toBeFocused();
    await page.keyboard.press("k");
    await expect(toggles.nth(0)).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(toggles.nth(0)).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("Enter");
    await expect(toggles.nth(0)).toHaveAttribute("aria-expanded", "false");
    await page.keyboard.press("f");
    await expect(page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" })).toBeChecked();
    await expect(toggles.nth(1)).toBeFocused();
    await marksDone(page);
    const tick = page.getByRole("checkbox", { name: /^Looks fine: uart_errors/ });
    await tick.click();                                                   // a tick box is no text field: K still moves
    await expect(tick).toBeChecked();
    await marksDone(page);
    await page.keyboard.press("k");
    await expect(toggles.nth(0)).toBeFocused();
  });

  test("in the last open row, F from its Looks fine button and Next flow › both leave focus on that row", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle");
    await page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" }).click();     // the other row is done
    await expect(page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" })).toBeChecked();
    await marksDone(page);
    await toggles.nth(1).click();
    const card = page.getByRole("region", { name: /^Flow 2: / });
    await card.getByRole("button", { name: "Looks fine", exact: true }).focus();
    await page.keyboard.press("f");                                       // no row is left to go to: the button goes with its mark
    await expect(page.getByRole("checkbox", { name: /^Looks fine: uart_errors/ })).toBeChecked();
    await expect(toggles.nth(1)).toBeFocused();
    await card.getByRole("button", { name: "Next flow ›" }).focus();
    await page.keyboard.press("Enter");                                   // the last row: Next flow › closes it, and the button goes with it
    await expect(toggles.nth(1)).toHaveAttribute("aria-expanded", "false");
    await expect(toggles.nth(1)).toBeFocused();
  });

  /** The marks the page asks for, one entry per request. */
  function watchMarks(page: Page): string[] {
    const asked: string[] = [];
    page.on("request", (r) => { if (r.method() === "POST" && r.url().endsWith("/checks/marks")) asked.push(r.url()); });
    return asked;
  }

  test("a held F marks one row, not row after row; Ctrl+F and Meta+F mark none", async ({ page }) => {
    const marks = watchMarks(page);
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle"), ticks = page.locator(".fl-tick");
    await expect(toggles).toHaveCount(2);
    await toggles.nth(0).focus();
    await page.keyboard.press("Control+f");                               // the browser's find and the platform's shortcut are not ours
    await page.keyboard.press("Meta+f");
    await page.waitForTimeout(300);                                       // a mark that wrongly started would have landed by now
    expect(marks).toHaveLength(0);
    await expect(ticks.nth(0)).not.toBeChecked();
    await page.keyboard.down("f");                                        // a fresh press marks row 1 and moves on to row 2
    await expect(ticks.nth(0)).toBeChecked();
    await marksDone(page);
    await page.keyboard.down("f");                                        // the key is still down: the browser's repeats are not presses
    await page.keyboard.down("f");
    await page.keyboard.up("f");
    await page.waitForTimeout(300);                                       // a mark that wrongly started would have landed by now
    expect(marks).toHaveLength(1);
    await expect(ticks.nth(1)).not.toBeChecked();
  });

  test("with the review menu or the How to read dialog open, J, K and F are the popup's, not the tab's", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle");
    await expect(toggles).toHaveCount(2);
    await page.keyboard.press("j");                                       // row 1 is the one the keys would act on
    await expect(toggles.nth(0)).toBeFocused();
    const menu = await reviewMenu(page);
    const item = menu.getByRole("menuitem").first();
    await expect(item).toBeFocused();
    for (const key of ["f", "j", "k"]) await page.keyboard.press(key);
    await page.waitForTimeout(300);                                       // a mark that wrongly started would have landed by now
    await expect(item).toBeFocused();
    await expect(menu).toBeVisible();
    await menu.getByRole("menuitem", { name: "How to read this page" }).click();
    const dialog = page.getByRole("dialog", { name: "How to read this page" });
    await expect(dialog).toBeFocused();
    for (const key of ["f", "j", "k"]) await page.keyboard.press(key);
    await page.waitForTimeout(300);
    await expect(dialog).toBeFocused();
    await expect(page.locator(".fl-tick:checked")).toHaveCount(0);
  });

  test("with Single-key shortcuts off, J, K and F do nothing on the Flows tab, Enter and Space still act, and switched on again the keys work", async ({ page }) => {
    const marks = watchMarks(page);
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle"), ticks = page.locator(".fl-tick");
    await expect(toggles).toHaveCount(2);
    await toggles.nth(0).focus();                                         // row 1 is the one J, K and F act from
    await setShortcuts(page, false);                                      // nothing on the tab is redrawn by this: the keys read the switch as they are pressed
    await page.keyboard.press("j");                                       // would go on to row 2
    await page.waitForTimeout(300);                                       // a step that wrongly started would have landed by now
    await expect(page.locator(".fl-toggle:focus"), "J moved the focus").toHaveCount(0);
    await page.reload();                                                  // the choice is kept: the keys meet it on a fresh page
    await expect(toggles).toHaveCount(2);
    await toggles.nth(1).focus();
    await page.keyboard.press("k");                                       // would go back to row 1
    await page.waitForTimeout(300);
    await expect(toggles.nth(1), "K moved the focus").toBeFocused();
    await toggles.nth(0).focus();
    await page.keyboard.press("f");                                       // would mark row 1 and move on to row 2
    await page.waitForTimeout(300);
    await expect(toggles.nth(0), "F moved the focus").toBeFocused();
    expect(marks, "F marked").toHaveLength(0);
    await expect(ticks.nth(0)).not.toBeChecked();
    await page.keyboard.press("Enter");                                   // the focused row's own button
    await expect(toggles.nth(0)).toHaveAttribute("aria-expanded", "true");
    await ticks.nth(1).focus();
    await page.keyboard.press("Space");                                   // and a tick box's own key
    await expect(ticks.nth(1)).toBeChecked();
    await marksDone(page);
    expect(marks).toHaveLength(1);
    await toggles.nth(1).focus();
    await setShortcuts(page, true);                                       // and again nothing on the tab is redrawn
    await page.keyboard.press("k");
    await expect(toggles.nth(0)).toBeFocused();
    await page.keyboard.press("j");
    await expect(toggles.nth(1)).toBeFocused();
    await toggles.nth(0).focus();
    await page.keyboard.press("f");
    await expect(ticks.nth(0)).toBeChecked();
    await marksDone(page);
    expect(marks).toHaveLength(2);
  });

  test("F says Marked fine in a hidden live region once its mark has landed, and says it again for the next row", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle"), said = page.locator('.st-flows [aria-live="polite"]');
    await expect(toggles).toHaveCount(2);
    await expect(said, "a polite live region that is there before F, and empty").toHaveText("");
    await expect(said, "for screen readers only").toHaveClass("vh");
    expect((await said.boundingBox())!.width).toBeLessThanOrEqual(1);
    const log = await recordSaid(said);
    await toggles.nth(0).focus();
    await page.keyboard.press("f");
    await expect(page.locator(".fl-tick").nth(0)).toBeChecked();
    await expect(said).toHaveText("Marked fine");
    await marksDone(page);
    await page.keyboard.press("f");                                       // F went on to row 2: the same words again, for its mark
    await expect(page.locator(".fl-tick").nth(1)).toBeChecked();
    await expect(said).toHaveText("Marked fine");
    await marksDone(page);
    expect(await log(), "emptied between the two, so a screen reader hears it twice").toEqual(["Marked fine", "", "Marked fine"]);
  });

  test("F on a row with nothing left open says nothing, and a mark the server refuses says nothing either", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle"), ticks = page.locator(".fl-tick"), said = page.locator('.st-flows [aria-live="polite"]');
    await expect(toggles).toHaveCount(2);
    await ticks.nth(0).click();                                           // row 1 is done by its tick box, which says nothing itself
    await expect(ticks.nth(0)).toBeChecked();
    await marksDone(page);
    await expect(said).toHaveText("");
    await toggles.nth(0).focus();
    await page.keyboard.press("f");                                       // nothing left to mark in row 1: F only moves on
    await expect(toggles.nth(1)).toBeFocused();
    await page.waitForTimeout(300);
    await expect(said).toHaveText("");
    await page.keyboard.press("f");                                       // row 2: marked, and said
    await expect(said).toHaveText("Marked fine");
    await marksDone(page);
    await ticks.nth(1).click();                                           // reopen it, then F meets a server that refuses
    await expect(ticks.nth(1)).not.toBeChecked();
    await marksDone(page);
    await page.route((u) => u.pathname.endsWith("/checks/marks"), (route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "The server could not mark them." }) }));
    await toggles.nth(1).focus();
    await page.keyboard.press("f");
    await expect(page.locator(".st-flows .banner.warn")).toHaveText("The server could not mark them.");
    await marksDone(page);
    await page.waitForTimeout(300);                                       // words that wrongly came after the refusal would be here by now
    await expect(said, "the old words are gone, and none came for a mark that did not land").toHaveText("");
    await expect(ticks.nth(1)).not.toBeChecked();
  });

  test("with storage blocked the shortcuts are on, the switch shows it and keeps nothing, and nothing throws (Review Focus 1)", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const base = await startReview(page, FOUR);
    await page.addInitScript(() => {
      Storage.prototype.getItem = () => { throw new Error("blocked"); };
      Storage.prototype.setItem = () => { throw new Error("blocked"); };
    });
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle");
    await expect(toggles).toHaveCount(2);
    await setShortcuts(page, false);                                      // a pick the browser cannot keep
    const menu = await reviewMenu(page);
    await expect(menu.getByRole("menuitemcheckbox", { name: "Single-key shortcuts" }), "the switch shows what the keys do").toHaveAttribute("aria-checked", "true");
    await page.keyboard.press("Escape");
    await toggles.nth(0).focus();
    await page.keyboard.press("j");
    await expect(toggles.nth(1)).toBeFocused();
    await page.keyboard.press("k");
    await expect(toggles.nth(0)).toBeFocused();
    expect(errors).toEqual([]);
  });

  test("F acts on the row whose tick box has focus", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle");
    const t1 = page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" });
    const t2 = page.getByRole("checkbox", { name: /^Looks fine: uart_errors/ });
    await expect(toggles).toHaveCount(2);
    await page.keyboard.press("j");                                       // row 1's toggle had focus last
    await expect(toggles.nth(0)).toBeFocused();
    await t2.focus();                                                     // then the reader tabs onto row 2's tick box
    await page.keyboard.press("f");
    await expect(t2).toBeChecked();
    await marksDone(page);
    await expect(t1).not.toBeChecked();
  });

  test("F acts on the row whose open card has focus", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle");
    const t1 = page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" });
    const t2 = page.getByRole("checkbox", { name: /^Looks fine: uart_errors/ });
    await expect(toggles).toHaveCount(2);
    await page.keyboard.press("j");
    await page.keyboard.press("j");
    await page.keyboard.press("Enter");                                   // opens row 2
    await expect(toggles.nth(1)).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("k");                                       // row 1's toggle has focus again; row 2's card stays open
    await expect(toggles.nth(0)).toBeFocused();
    await page.getByRole("region", { name: /^Flow 2: / }).getByRole("button", { name: "Looks fine", exact: true }).focus();
    await page.keyboard.press("f");
    await expect(t2).toBeChecked();
    await marksDone(page);
    await expect(t1).not.toBeChecked();
  });

  test("a click on a toggle that does not take focus (Safari, Firefox on macOS) still makes its row the one F acts on", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle");
    const t1 = page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" });
    const t2 = page.getByRole("checkbox", { name: /^Looks fine: uart_errors/ });
    await expect(toggles).toHaveCount(2);
    await page.keyboard.press("j");                                       // row 1's toggle has focus
    await expect(toggles.nth(0)).toBeFocused();
    await toggles.nth(1).dispatchEvent("click");                          // opens row 2 and leaves focus where it was
    await expect(toggles.nth(1)).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("f");                                       // the reader means the row they opened
    await expect(t2).toBeChecked();
    await marksDone(page);
    await expect(t1).not.toBeChecked();
  });

  test("a click on a tick box that does not take focus still makes its row the one F acts on", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const toggles = page.locator(".fl-toggle");
    const t1 = page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" });
    const t2 = page.getByRole("checkbox", { name: /^Looks fine: uart_errors/ });
    await expect(toggles).toHaveCount(2);
    await page.keyboard.press("j");                                       // row 1's toggle has focus
    await expect(toggles.nth(0)).toBeFocused();
    await t2.dispatchEvent("click");                                      // marks row 2 and leaves focus where it was
    await expect(t2).toBeChecked();
    await marksDone(page);
    await t2.dispatchEvent("click");                                      // and reopens it
    await expect(t2).not.toBeChecked();
    await marksDone(page);
    await page.keyboard.press("f");                                       // row 2 is the one the reader last worked on
    await expect(t2).toBeChecked();
    await marksDone(page);
    await expect(t1).not.toBeChecked();
  });

  test("while a mark is on its way every tick box is dimmed and shows a progress cursor, stays enabled, and a click on another is dropped", async ({ page }) => {
    const marks = watchMarks(page);
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const ticks = page.locator(".fl-tick");
    await expect(ticks).toHaveCount(2);
    await expect(ticks.nth(1)).toHaveCSS("opacity", "1");
    let release = () => {};
    const gate = new Promise<void>((done) => { release = done; });
    await page.route((u) => u.pathname.endsWith("/checks/marks"), async (route) => { await gate; await route.continue(); });
    await ticks.nth(0).click();
    await expect(page.locator(".st-flows")).toHaveAttribute("aria-busy", "true");
    for (const i of [0, 1]) {
      await expect(ticks.nth(i)).toBeEnabled();                           // enabled, so a tick box keeps the focus it has
      await expect(ticks.nth(i)).toHaveCSS("opacity", "0.5");
      await expect(ticks.nth(i)).toHaveCSS("cursor", "progress");
    }
    await ticks.nth(1).click();                                           // dropped, not queued
    release();
    await expect(ticks.nth(0)).toBeChecked();
    await marksDone(page);
    for (const i of [0, 1]) {
      await expect(ticks.nth(i)).toHaveCSS("opacity", "1");
      await expect(ticks.nth(i)).not.toHaveCSS("cursor", "progress");
    }
    await page.waitForTimeout(300);                                       // a queued click would have been sent by now
    expect(marks).toHaveLength(1);
    await expect(ticks.nth(1)).not.toBeChecked();
  });

  /** The marks and unmarks the page sends to the server (the "Looks fine" and "Reopen" requests), one entry each. */
  function watchChecks(page: Page) {
    const sent: string[] = [];
    page.on("request", (r) => {
      const at = r.url().indexOf("/checks/");
      if (at >= 0 && r.method() !== "GET") sent.push(`${r.method()} ${r.url().slice(at + 8).replace(/^.*\/mark$/, "<key>/mark")}`);
    });
    return sent;
  }
  /** The keys marked fine now, as the server has them. */
  const marked = async (page: Page, base: string): Promise<string[]> =>
    Object.keys((await (await page.request.get(`/api/reviews/${base.split("/")[2]}/reading`)).json()).marks).sort();

  test("Reopen on a row with two marked places sends one request and reopens them both", async ({ page }) => {
    await withTwoPlaces(page);
    const sent = watchChecks(page);
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const tick = page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" });
    await page.locator(".fl-toggle").first().click();
    const card = page.getByRole("region", { name: /^Flow 1: / });
    await card.getByRole("button", { name: "Looks fine", exact: true }).click();
    await expect(tick).toBeChecked();
    await marksDone(page);
    expect(await marked(page, base)).toHaveLength(2);                          // both places of the row
    sent.length = 0;
    await card.getByRole("button", { name: "Reopen", exact: true }).click();
    await expect(tick).not.toBeChecked();
    await marksDone(page);
    expect(sent).toEqual(["POST unmarks"]);                                    // one request for both places, not one each
    expect(await marked(page, base)).toEqual([]);
    await tick.click();                                                        // the tick box reopens a row the same way
    await expect(tick).toBeChecked();
    await marksDone(page);
    sent.length = 0;
    await tick.click();
    await expect(tick).not.toBeChecked();
    await marksDone(page);
    expect(sent).toEqual(["POST unmarks"]);
    expect(await marked(page, base)).toEqual([]);
  });

  test("a Reopen the server refuses shows its error and leaves the row's marks as they were", async ({ page }) => {
    await withTwoPlaces(page);
    const sent = watchChecks(page);
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const tick = page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" });
    await page.locator(".fl-toggle").first().click();
    const card = page.getByRole("region", { name: /^Flow 1: / });
    await card.getByRole("button", { name: "Looks fine", exact: true }).click();
    await expect(tick).toBeChecked();
    await marksDone(page);
    const before = await marked(page, base);
    expect(before).toHaveLength(2);
    await page.route((u) => u.pathname.endsWith("/checks/unmarks"), (route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "The server could not reopen them." }) }));
    sent.length = 0;
    await card.getByRole("button", { name: "Reopen", exact: true }).click();
    await expect(page.locator(".st-flows .banner.warn")).toHaveText("The server could not reopen them.");
    await marksDone(page);
    expect(sent).toEqual(["POST unmarks"]);                                    // nothing else was sent: no key went on its own
    await expect(tick).toBeChecked();                                          // the row still reads done, and Reopen is still there
    await expect(card.getByRole("button", { name: "Reopen", exact: true })).toBeVisible();
    expect(await marked(page, base)).toEqual(before);                          // and so does the server
    await tick.click();                                                        // the tick box meets the same refusal
    await expect(page.locator(".st-flows .banner.warn")).toHaveText("The server could not reopen them.");
    await marksDone(page);
    await expect(tick).toBeChecked();
    expect(await marked(page, base)).toEqual(before);
  });

  test("a J pressed the moment the rows show is heard, not lost to the next paint", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.addInitScript(() => {
      new MutationObserver((_, watcher) => {
        if (!document.querySelector(".fl-toggle")) return;
        watcher.disconnect();
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "j" }));   // in the microtask after the commit that shows the rows
      }).observe(document, { childList: true, subtree: true });
    });
    await page.goto(`${base}/s/S1`);
    await expect(page.locator(".fl-toggle").first()).toBeFocused();
  });

  test("a tick box takes a press anywhere in a 24px square around it, not only on its 13px box (WCAG 2.5.8)", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const tick = page.getByRole("checkbox", { name: "Looks fine: logger_flush ignores -2" });
    await tick.scrollIntoViewIfNeeded();                                  // a press goes to a point on the screen
    const { target, box } = await clickable(tick);
    expect(target.width, "the tick's target is wide enough").toBeGreaterThanOrEqual(24);
    expect(target.height, "the tick's target is tall enough").toBeGreaterThanOrEqual(24);
    const x = target.x + 2, y = target.y + 2;                             // a corner of the target, off the box itself
    expect(x < box.x || y < box.y).toBe(true);
    await page.mouse.click(x, y);
    await expect(tick).toBeChecked();
    await marksDone(page);
    await page.mouse.click(x, y);                                         // and a second press there reopens it
    await expect(tick).not.toBeChecked();
    await expect(page.locator(".fl-toggle").first()).toHaveAttribute("aria-expanded", "false");   // the row's toggle is a separate target
  });

  test("only a group line forces its row open: the Flows tab and the story's own row, links to the address the reader is at, do not", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    const outline = page.locator("aside.ws-outline"), toggles = page.locator(".fl-toggle");
    await outline.getByRole("link", { name: /^Go to Uart::errors · 1 flow/ }).click();
    await expect(page).toHaveURL(/\/s\/S1\?flow=2$/);
    await expect(toggles.nth(1)).toHaveAttribute("aria-expanded", "true");
    await toggles.nth(1).click();                                                    // the reader closes it; the address still says flow=2
    await expect(toggles.nth(1)).toHaveAttribute("aria-expanded", "false");
    for (const link of [page.getByRole("navigation", { name: "Story sections" }).getByRole("link", { name: /^Flows/ }),
                        outline.getByRole("link", { name: /^Go to story S1/ })]) {
      await link.click();
      await expect(page).toHaveURL(/\/s\/S1\?flow=2$/);
      await page.waitForTimeout(300);                                                // a row that wrongly opened would have by now
      await expect(toggles.nth(1)).toHaveAttribute("aria-expanded", "false");
    }
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

  test("the end line shows eight checks and Show N more, which shows the rest and puts focus on the first it shows", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const also = page.getByRole("region", { name: "Also in this story" }), chips = also.locator(".st-chip");
    await expect(chips).toHaveCount(8);                                              // of 41: not a wall
    await expect(chips.nth(6)).toHaveText("26 functions no test calls");
    const more = also.getByRole("button", { name: "Show 33 more" });
    await expect(more).toHaveClass(/\blink\b/);
    await more.focus();
    await page.keyboard.press("Enter");
    await expect(chips).toHaveCount(41);
    await expect(also.getByRole("button", { name: /^Show \d+ more$/ })).toHaveCount(0);
    await expect(chips.nth(8)).toBeFocused();                                        // the button went: focus is on the ninth chip, not the page
    await page.keyboard.press("Tab");                                                // the chips are links: Tab walks them
    await expect(chips.nth(9)).toBeFocused();
    await expect(chips.nth(9)).toHaveText("2 callers handle regs_a1's result the old way");
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

  test("J or F onto a folded row unfolds its group and focuses the row, and K back leaves the group unfolded", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const groups = page.locator("section.fl-group"), first = groups.first(), second = groups.nth(1);
    await first.locator(".fl-toggle").nth(7).focus();                                // the eighth row, the last showing
    await expect(first.locator(".fl-row")).toHaveCount(8);
    await page.keyboard.press("j");
    await expect(first.locator(".fl-row")).toHaveCount(25);                          // the ninth was hidden: reaching it unfolds its group
    await expect(first.locator(".fl-more")).toHaveCount(0);
    await expect(first.locator(".fl-toggle").nth(8)).toBeFocused();
    await page.keyboard.press("k");
    await expect(first.locator(".fl-toggle").nth(7)).toBeFocused();
    await expect(first.locator(".fl-row")).toHaveCount(25);                          // and K back does not fold it again
    await second.locator(".fl-toggle").nth(7).focus();
    await expect(second.locator(".fl-row")).toHaveCount(8);
    await page.keyboard.press("f");                                                  // the next row with a place open is the ninth, hidden
    await expect(second.locator(".fl-tick").nth(7)).toBeChecked();
    await expect(second.locator(".fl-row")).toHaveCount(25);
    await expect(second.locator(".fl-toggle").nth(8)).toBeFocused();
  });

  test("F on the last row with something open wraps to the first row above with something open", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    for (const n of [1, 2]) {                                                        // the first two rows are done, so the wrap has to pass them
      await page.locator(`#flow-${n} .fl-tick`).click();
      await expect(page.locator(`#flow-${n} .fl-tick`)).toBeChecked();
      await marksDone(page);
    }
    await page.goto(`${base}/s/S1?flow=140`);                                        // the last row of the tab, in a group that was folded
    await expect(page.locator("#flow-140 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("f");
    await expect(page.locator("#flow-140 .fl-tick")).toBeChecked();
    await expect(page.locator("#flow-3 .fl-toggle")).toBeFocused();                  // not row 1 or 2: they have nothing open
    await marksDone(page);
    await expect(page.locator("#flow-3 .fl-tick")).not.toBeChecked();                // F marks the row it leaves, not the one it goes to
    await expect(page.locator("#flow-1 .fl-tick:checked, #flow-2 .fl-tick:checked")).toHaveCount(2);
  });

  test("a click on an outline group line for another flow scrolls its row into view once", async ({ page }) => {
    await page.addInitScript(() => {                                                 // which elements the page scrolled into view
      const scrolled: string[] = [];
      (window as unknown as { scrolled: string[] }).scrolled = scrolled;
      const scrollIntoView = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = function (this: Element, arg?: boolean | ScrollIntoViewOptions) {
        scrolled.push(this.id);
        return scrollIntoView.call(this, arg);
      };
    });
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const scrolls = (id: string) => page.evaluate((x) => (window as unknown as { scrolled: string[] }).scrolled.filter((i) => i === x).length, id);
    expect(await scrolls("flow-51")).toBe(0);
    await page.locator("aside.ws-outline .ws-flows .ws-row").nth(2).click();         // the third group: flows 51 to 75
    await expect(page.locator("#flow-51 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await page.waitForTimeout(300);                                                  // a second scroll would have been made by now
    expect(await scrolls("flow-51")).toBe(1);
    await page.locator("aside.ws-outline .ws-flows .ws-row").nth(4).click();         // and again for the fifth: flows 101 to 125
    await expect(page.locator("#flow-101 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await page.waitForTimeout(300);
    expect(await scrolls("flow-101")).toBe(1);
    expect(await scrolls("flow-51")).toBe(1);
  });

  test("at 1280px rows stay a line each, well under 44px apart (the touch size is for phones)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const rows = page.locator("section.fl-group").first().locator(".fl-row");
    await expect(rows).toHaveCount(8);
    const tops = await rows.evaluateAll((els) => els.map((e) => e.getBoundingClientRect().top));
    const gaps = tops.slice(1).map((t, i) => t - tops[i]);
    expect(Math.max(...gaps), `pitch ${gaps.join(", ")}`).toBeLessThan(44);
    expect(Math.min(...gaps), `pitch ${gaps.join(", ")}`).toBeGreaterThan(24);        // and a row is not squeezed either
  });

  test("while a check is open beside the page J, K and F are the stepper's, and letters in its comment box (Review Focus 4)", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const readers = "5 places read UartDev::errors, which uart_a1 now writes";
    await page.getByRole("link", { name: `Open check: ${readers}` }).click();
    const panel = page.getByRole("complementary", { name: `Check: ${readers}` });
    await expect(panel.locator(".cs-pos")).toHaveText("1 / 5");
    await page.keyboard.press("j");
    await expect(panel.locator(".cs-pos")).toHaveText("2 / 5");
    await page.keyboard.press("f");
    await expect(panel.locator(".cs-pos")).toHaveText("3 / 5");
    await expect(page.getByRole("checkbox", { name: "Looks fine: uart_d2 sees a new writer of UartDev::errors · via uart_a1" })).toBeChecked();
    await expect(page.locator(".fl-toggle:focus")).toHaveCount(0);
    await expect(page.locator(".fl-row.on")).toHaveCount(0);
    await panel.getByRole("button", { name: "Comment" }).click();
    const box = panel.getByPlaceholder("Leave a comment…");
    await box.pressSequentially("jkf");
    await expect(box).toHaveValue("jkf");
    await expect(panel.locator(".cs-pos")).toHaveText("3 / 5");
    await expect(page.locator(".fl-toggle:focus")).toHaveCount(0);
    await panel.getByRole("link", { name: "Close the check" }).click();
    await expect(panel).toHaveCount(0);
    await page.keyboard.press("j");                                       // the panel closed: the keys are the tab's again
    await expect(page.locator(".fl-toggle").first()).toBeFocused();
  });

  test("with the keyboard alone, focus stays on a tick whose mark lands and goes to a row's toggle after Next flow ›, Show N more, Looks fine and Reopen", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const first = page.locator("section.fl-group").first(), toggles = first.locator(".fl-toggle"), ticks = first.locator(".fl-tick");
    await expect(first.locator(".fl-row")).toHaveCount(8);
    // a tick box takes Space; while its mark is on its way it stays enabled and focused, the tab says it is busy, and J waits
    let release = () => {};
    const gate = new Promise<void>((done) => { release = done; });
    await page.route((u) => u.pathname.endsWith("/checks/marks"), async (route) => { await gate; await route.continue(); });
    await ticks.first().focus();
    await page.keyboard.press("Space");
    await expect(page.locator(".st-flows")).toHaveAttribute("aria-busy", "true");
    await expect(ticks.first()).toBeEnabled();
    await expect(ticks.first()).toBeFocused();
    await page.keyboard.press("j");
    await page.waitForTimeout(300);                                       // the mark is held: nothing moves
    await expect(ticks.first()).toBeFocused();
    release();
    await expect(ticks.first()).toBeChecked();
    await marksDone(page);
    await expect(ticks.first()).toBeFocused();
    // Next flow › opens the next row and puts focus on its toggle, the row J and K go on from
    await toggles.nth(0).focus();
    await page.keyboard.press("Enter");
    await expect(toggles.nth(0)).toHaveAttribute("aria-expanded", "true");
    await first.getByRole("region", { name: /^Flow \d+: / }).getByRole("button", { name: "Next flow ›" }).focus();
    await page.keyboard.press("Enter");
    await expect(toggles.nth(1)).toHaveAttribute("aria-expanded", "true");
    await expect(toggles.nth(1)).toBeFocused();
    await page.keyboard.press("j");
    await expect(toggles.nth(2)).toBeFocused();
    // Show N more puts focus on the first row it reveals
    await first.getByRole("button", { name: "Show 17 more" }).focus();
    await page.keyboard.press("Enter");
    await expect(first.locator(".fl-row")).toHaveCount(25);
    await expect(toggles.nth(8)).toBeFocused();
    await page.keyboard.press("j");
    await expect(toggles.nth(9)).toBeFocused();
    // Looks fine and Reopen, in the open row, leave focus on that row's toggle
    const row = first.locator(".fl-row").nth(1);
    await row.getByRole("button", { name: "Looks fine", exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(row.locator(".fl-tick")).toBeChecked();
    await expect(row.locator(".fl-toggle")).toBeFocused();
    await marksDone(page);
    await row.getByRole("button", { name: "Reopen", exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(row.locator(".fl-tick")).not.toBeChecked();
    await expect(row.locator(".fl-toggle")).toBeFocused();
  });

  test("under the current story the outline lists a line per flow group, not per flow", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const rows = page.locator("aside.ws-outline .ws-flows .ws-row");
    await expect(rows).toHaveCount(6);                                               // not 140
    await expect(rows.first()).toHaveAttribute("aria-label", "Go to TelemDev::errors · 25 flows, 25 open");
    await expect(rows.first()).toHaveAttribute("title", "TelemDev::errors · 25 flows");
    await rows.nth(2).click();
    await expect(page).toHaveURL(/\/s\/S1\?flow=51$/);
    await expect(page.locator("#flow-51 .fl-toggle")).toHaveAttribute("aria-expanded", "true");
    await expect(rows.nth(2)).toHaveAttribute("aria-current", "true");
  });

  test("a click on an outline group line opens its first row and brings it into view, though the address already names it", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const line = page.locator("aside.ws-outline .ws-flows .ws-row").nth(2);          // the third group: flows 51 to 75
    const first = page.locator("#flow-51 .fl-toggle"), other = page.locator("#flow-52 .fl-toggle");
    await line.click();
    await expect(page).toHaveURL(/\/s\/S1\?flow=51$/);
    await expect(first).toHaveAttribute("aria-expanded", "true");
    await other.click();                                                             // another row opens; the address still says flow=51
    await expect(other).toHaveAttribute("aria-expanded", "true");
    await expect(first).toHaveAttribute("aria-expanded", "false");
    await page.getByRole("region", { name: "Also in this story" }).scrollIntoViewIfNeeded();   // far from the group
    await expect(page.locator("#flow-51")).not.toBeInViewport();
    await line.click();                                                              // the link is to the address the reader is at: it still works
    await expect(page).toHaveURL(/\/s\/S1\?flow=51$/);
    await expect(first).toHaveAttribute("aria-expanded", "true");
    await expect(other).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByRole("region", { name: /^Flow 51: / })).toBeInViewport();
    await line.click();                                                              // with its row open and in view it opens nothing more, and does not close it
    await expect(first).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("region", { name: /^Flow 51: / })).toBeInViewport();
  });

  /** Row 51 opened by its group line in the outline and closed again by the reader, the page scrolled to the end of the tab, far from
   * it. `quiet` says that nothing has opened the row or scrolled to it since. */
  async function closedRowFarAway(page: Page) {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const first = page.locator("#flow-51 .fl-toggle"), also = page.getByRole("region", { name: "Also in this story" });
    await page.locator("aside.ws-outline .ws-flows .ws-row").nth(2).click();
    await expect(first).toHaveAttribute("aria-expanded", "true");
    await first.click();                                                             // the reader closes it; the address still says flow=51
    await expect(first).toHaveAttribute("aria-expanded", "false");
    await also.scrollIntoViewIfNeeded();
    await expect(page.locator("#flow-51")).not.toBeInViewport();
    const quiet = async () => {
      await page.waitForTimeout(300);                                                // a row that wrongly opened would have by now
      await expect(first).toHaveAttribute("aria-expanded", "false");
      await expect(page.locator("#flow-51")).not.toBeInViewport();
    };
    return { also, quiet };
  }

  test("a row the reader closed stays closed, and the page stays put, while a check opens and closes in the side panel and Back and Forward step over it", async ({ page }) => {
    const { also, quiet } = await closedRowFarAway(page);
    const text = "26 functions no test calls";
    await also.getByRole("link", { name: `Open check: ${text}` }).click();
    const panel = page.getByRole("complementary", { name: `Check: ${text}` });
    await expect(panel).toBeVisible();
    await expect(page).toHaveURL(/\?flow=51&open=cause%3Ac[0-9a-f]{10}&at=1$/);
    await quiet();
    await panel.getByRole("link", { name: "Close the check" }).click();
    await expect(panel).toHaveCount(0);
    await expect(page).toHaveURL(/\/s\/S1\?flow=51$/);
    await quiet();
    await page.goBack();                                                             // back to the check opened beside the page
    await expect(panel).toBeVisible();
    await quiet();
    await page.goBack();                                                             // and to the entry the group line made, which still holds its click
    await expect(panel).toHaveCount(0);
    await expect(page).toHaveURL(/\/s\/S1\?flow=51$/);
    await quiet();
    await page.goForward();
    await expect(panel).toBeVisible();
    await quiet();
    await page.goForward();
    await expect(panel).toHaveCount(0);
    await quiet();
  });

  test("a row the reader closed stays closed, and the page stays put, while the side panel's tabs are opened, switched and closed", async ({ page }) => {
    const { also, quiet } = await closedRowFarAway(page);
    const one = "26 functions no test calls", other = "2 callers handle regs_a1";
    await also.getByRole("link", { name: `Open check: ${one}` }).click();
    await expect(page.getByRole("complementary", { name: `Check: ${one}` })).toBeVisible();
    await also.getByRole("button", { name: "Show 33 more" }).click();                // the other is past the end line's first eight
    await also.getByRole("link", { name: new RegExp(`^Open check: ${other}`) }).click();
    const tabs = page.getByRole("list", { name: "Open items" });
    await expect(tabs.getByRole("link")).toHaveCount(2);                             // a tab for each check
    await expect(page.getByRole("complementary", { name: new RegExp(`^Check: ${other}`) })).toBeVisible();
    await quiet();
    await tabs.getByRole("link").first().click();                                    // a tab switch, and back
    await expect(page.getByRole("complementary", { name: `Check: ${one}` })).toBeVisible();
    await quiet();
    await tabs.getByRole("link").last().click();
    await expect(page.getByRole("complementary", { name: new RegExp(`^Check: ${other}`) })).toBeVisible();
    await quiet();
    await tabs.getByRole("button", { name: /^Close / }).last().click();              // closing a tab steps to the other without a new entry
    await expect(page.getByRole("complementary", { name: `Check: ${one}` })).toBeVisible();
    await quiet();
    await page.getByRole("complementary", { name: `Check: ${one}` }).getByRole("link", { name: "Close the check" }).click();
    await expect(page.getByRole("complementary", { name: /^Check: / })).toHaveCount(0);
    await quiet();
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
    // A row is readable only when its button sits inside it and its sentence has room (`.fl-one` is nowrap: it can't wrap, it can vanish).
    const unreadable = () => page.locator(".fl-row").evaluateAll((rows) => rows.filter((r) => {
      const b = r.getBoundingClientRect(), t = r.querySelector(".fl-toggle")!.getBoundingClientRect(), o = r.querySelector(".fl-one")!.getBoundingClientRect();
      return t.right > b.right + 1 || o.width < 40;
    }).length);
    await expect(page.getByRole("region", { name: "Also in this story" })).toBeVisible();   // its chips are on this page
    expect(await wrapped()).toBe(0);
    expect(await unreadable()).toBe(0);
    expect(await sideways(page)).toBeLessThanOrEqual(0);
    await page.locator(".fl-toggle").first().click();
    await expect(page.getByRole("region", { name: /^Flow 1: / })).toBeVisible();
    expect(await wrapped()).toBe(0);
    expect(await unreadable()).toBe(0);
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });

  test("rows are at least 44px apart and each tick's label is as tall as its row, so a finger lands on its own row (owner decision 1)", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const rows = page.locator("section.fl-group").first().locator(".fl-row");
    await expect(rows).toHaveCount(8);
    const tops = await rows.evaluateAll((els) => els.map((e) => e.getBoundingClientRect().top));
    const gaps = tops.slice(1).map((t, i) => t - tops[i]);
    expect(Math.min(...gaps), `pitch ${gaps.join(", ")}`).toBeGreaterThanOrEqual(44);
    const lines = await page.locator(".fl-head").evaluateAll((els) => els.map((e) => ({
      line: e.querySelector(".fl-toggle")!.getBoundingClientRect().height, tick: e.querySelector("label.fl-tickbox")!.getBoundingClientRect().height })));
    expect(lines.length).toBe(48);                                                    // every row showing, in all six groups
    for (const { line, tick } of lines) {
      expect(line).toBeGreaterThanOrEqual(44);
      expect(tick).toBeGreaterThanOrEqual(44);
      expect(tick).toBeCloseTo(line, 0);                                              // the label spans the row's line, no more, no less
    }
  });

  test("a tick box's target is a 24px square here too, and a click on its edge ticks it", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);
    const tick = page.locator(".fl-tick").first();
    await tick.scrollIntoViewIfNeeded();                                  // a click goes to a point on the screen
    const { target, box } = await clickable(tick);
    expect(target.width, "the tick's target is wide enough").toBeGreaterThanOrEqual(24);
    expect(target.height, "the tick's target is tall enough").toBeGreaterThanOrEqual(24);
    const x = target.x + 2, y = target.y + target.height - 2;             // a corner of the target, off the box itself
    expect(x < box.x || y > box.y + box.height).toBe(true);
    // a mouse click, not a tap: Chromium moves a tap to the clickable thing it judges nearest (a tap here lands on the next
    // row's box), so a tap tests its touch adjustment rather than where this box takes presses
    await page.mouse.click(x, y);
    await expect(tick).toBeChecked();
  });
});

test.describe("the Flows tab with AI", () => {
  test.use({ baseURL: "http://127.0.0.1:8798", viewport: { width: 1440, height: 900 } });

  test("J, K and F are letters in the story's question box, and move rows again once it loses focus (Review Focus 4)", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/s/S1`);
    await expect(page.locator(".fl-toggle").first()).toBeVisible();
    await explainItem(page.locator(".ws-story-head"), "Ask a question…");
    const box = page.getByRole("textbox", { name: "What should the AI explain?" });
    await box.pressSequentially("jkf");
    await expect(box).toHaveValue("jkf");
    await expect(page.locator(".fl-toggle:focus")).toHaveCount(0);
    await expect(page.locator(".fl-tick:checked")).toHaveCount(0);
    await box.blur();
    await page.keyboard.press("j");
    await expect(page.locator(".fl-toggle").first()).toBeFocused();
  });
});
