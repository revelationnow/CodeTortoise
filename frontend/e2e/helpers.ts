import { expect, type Locator, type Page } from "@playwright/test";

// The fixture servers beyond the default one: playwright.config.ts starts them, and a spec picks one with `test.use({ baseURL })`.

/** CodeTortoise with the fake model in e2e/fake_llm.py (e2e/serve-ai.sh). */
export const AI = "http://127.0.0.1:8798";
/** Stories and risk review by the fake strong model, targets hal and fw (e2e/serve-strong.sh). */
export const STRONG = "http://127.0.0.1:8795";
/** The generated large fixture, CLs 201 and 202 (e2e/serve-large.sh): one thread, whose first story has 140 flows in six groups, and a Tests row. */
export const LARGE = "http://127.0.0.1:8796";
/** The server whose tortoise.yaml lists Stats::* as shared sinks (e2e/serve-sinks.sh): its Coverage has the Show/Hide line. */
export const SINKS = "http://127.0.0.1:8794";

export async function login(page: Page, user = "demo") {
  await page.goto("/login");
  await page.getByLabel("P4 user").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();
}

/** Holds the server's answers to `url` back until `release()`, which lets through those held and those to come; `held`
 * settles once one is being held. A later `hold` of the same address takes over from this one. */
export async function hold(page: Page, url: string): Promise<{ held: Promise<void>; release: () => void }> {
  let entered = () => {}, release = () => {};
  const held = new Promise<void>((r) => { entered = r; }), gate = new Promise<void>((r) => { release = r; });
  await page.route(url, async (route) => {
    entered();
    await gate;
    try { await route.continue(); } catch { /* the page went away while it was held */ }
  });
  return { held, release };
}

/** Log in as the demo owner, review fixture CLs 101+102 (the large fixture's are 201 202) from the landing page and
 * wait for the rail's stories; returns the review's address ("/r/12"). */
export async function startReview(page: Page, cls = "101 102"): Promise<string> {
  await login(page);
  await page.getByLabel("Changelists (shelved or submitted)").fill(cls);
  await page.getByRole("button", { name: "Start review" }).click();
  await railReady(page);
  return page.url().match(/\/r\/\d+/)![0];
}

/** Serves the review as one stored before readings: its `/reading` is a 404 that says to re-run. `rid` is the review's number ("12"). */
export function noReading(page: Page, rid: string) {
  return page.route(`**/api/reviews/${rid}/reading`, (r) =>
    r.fulfill({ status: 404, json: { detail: "this review has no reading: re-run it" } }));
}

/** With uart.c's diff open in the detail panel, starts a comment on its new `return -2;` line (stacked view); returns the panel, the thread
 * that opens under the line and the thread's box. */
export async function commentOnReturn(page: Page): Promise<{ viewer: Locator; thread: Locator; box: Locator }> {
  const viewer = page.getByRole("complementary", { name: "Code: uart.c" });
  await viewer.getByRole("button", { name: "Stacked" }).click();
  await viewer.locator(".bd-ln.a", { hasText: "return -2;" }).first().click();
  const thread = viewer.locator(".bd-thread"), box = thread.getByPlaceholder("Leave a comment…");
  await expect(box).toBeVisible();
  return { viewer, thread, box };
}

/** Waits for the outline's first thread bar or story row (a review without threads, or before the reading, has rows). */
export async function railReady(page: Page) {
  const rail = page.locator(".ws-rail");
  await expect(rail.getByRole("button", { name: /^Thread \w+:/ }).or(rail.getByRole("link", { name: /^Go to story/ })).first())
    .toBeVisible({ timeout: 60_000 });
}

/** A story's row in the outline, opening thread bars in turn until it shows (spec 2026-10-25-review-ui-redesign §6: one
 * thread open at a time). The stories can load after the reading, so a list may be empty for a moment: it goes round the bars, each
 * given a moment, until the row shows or `startReview`'s minute for the outline is up, so no bar costs more than that moment. */
export async function storyLink(page: Page, name: RegExp): Promise<Locator> {
  const rail = page.locator(".ws-rail"), link = rail.getByRole("link", { name }).first();
  const bars = rail.getByRole("button", { name: /^Thread \w+:/ });
  await expect(bars.or(link).first()).toBeVisible({ timeout: 60_000 });
  if (await link.isVisible()) return link;
  const n = await bars.count();
  if (!n) return link;                                  // the bars are gone (the outline drew again) and the loop below would only spin: the caller's own wait on the link decides
  for (const end = Date.now() + 60_000; Date.now() < end;) {
    for (let i = 0; i < n; i++) {
      const bar = bars.nth(i);
      if ((await bar.getAttribute("aria-expanded")) !== "true") await bar.click();
      if (await link.waitFor({ state: "visible", timeout: 750 }).then(() => true, () => false)) return link;
    }
  }
  return link;
}

/** The outline's thread bars' names, top to bottom. */
export const barNames = (page: Page) =>
  page.locator(".ws-rail .ws-bar > button").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")));

/** No node id is ever shown (spec §8): visible text never matches N<digits>. */
export async function expectNoNodeIds(page: Page) {
  const text = await page.locator("main").innerText();
  expect(text.match(/\bN\d+\b/g) ?? []).toEqual([]);
}

/** Every link and button on the page has an accessible name (spec §8). */
export async function expectNamed(page: Page) {
  const unnamed = await page.locator("main a, main button, main [role=button]").evaluateAll((els) =>
    els.filter((e) => !(e.getAttribute("aria-label") || e.textContent?.trim() || e.getAttribute("title")))
       .map((e) => e.outerHTML.slice(0, 120)));
  expect(unnamed).toEqual([]);
}

/** Opens one of the overview's folded rows (spec 2026-10-25-review-ui-redesign §5.3) if it is shut; returns its region. */
export async function openFold(page: Page, name: "Build impact" | "Coverage" | "Discussion"): Promise<Locator> {
  const region = page.getByRole("region", { name, exact: true }), fold = region.locator("details.ov-fold");
  await expect(fold).toBeVisible();
  if ((await fold.getAttribute("open")) === null) await region.locator("summary").click();
  await expect(fold).toHaveAttribute("open", "");
  return region;
}

/** The flow strip's ‹ › keep their place across flows and its row never scrolls sideways (spec §3.6, §8). */
export async function flowStripHolds(page: Page) {
  const strip = page.getByRole("region", { name: "Flow" });
  const next = strip.getByRole("button", { name: "Next flow" });
  const at = (await next.boundingBox())!.x;
  const row = strip.locator(".ws-flow-row");
  for (let i = 0; i < 3; i++) {
    expect(await row.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    await next.click();
    expect((await next.boundingBox())!.x).toBe(at);
  }
}

/** The workspace's scrollers, by class: the page, the outline's rows and the detail panel's body. `sideways` reads these, and the
 * layout spec pins that each is there once on a story page with a panel open, so a renamed scroller cannot drop out of it unseen. */
export const SCROLLERS = [".ws-page", ".ws-rail-scroll", ".ws-detail-body"];

/** How far the page scrolls sideways at most: the largest `scrollWidth - clientWidth` over the document and over each of the workspace's
 * `SCROLLERS` on the page. In the workspace the document never scrolls (`main` and the centre clip), so the document alone measures
 * nothing there; the overflow is on these. A scroller that clips (`overflow-x: hidden`) counts too: what it hides is still too wide.
 * Above zero is a real overflow: fix the CSS, never the check. */
export async function sideways(page: Page): Promise<number> {
  return page.evaluate((selector) => {
    const scrollers = [document.documentElement, ...document.querySelectorAll(selector)];
    return Math.max(...scrollers.map((e) => e.scrollWidth - e.clientWidth));
  }, SCROLLERS.join(", "));
}

/** WCAG contrast ratio between an element's text colour and the first opaque background behind it. */
export async function contrast(page: Page, selector: string) {
  return page.locator(selector).first().evaluate((el) => {
    // rgb(0-255…) or, for color-mix() backgrounds, color(srgb 0-1…)
    const rgb = (c: string) => (c.match(/[\d.]+/g) ?? []).map(Number).map((v, i) => c.startsWith("color(") && i < 3 ? v * 255 : v);
    const lum = ([r, g, b]: number[]) => {
      const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    let bgEl: Element | null = el, bg = "";
    while (bgEl) {
      const c = getComputedStyle(bgEl).backgroundColor, a = rgb(c)[3];
      if (c && c !== "transparent" && (a === undefined || a > 0.9)) { bg = c; break; }
      bgEl = bgEl.parentElement;
    }
    const fg = lum(rgb(getComputedStyle(el).color)), b = lum(rgb(bg || "rgb(255,255,255)"));
    return (Math.max(fg, b) + 0.05) / (Math.min(fg, b) + 0.05);
  });
}

/** Each button is an icon with a name: no visible text, an svg, and a tooltip that says what it does. */
export async function expectIconsOnly(buttons: Locator) {
  const n = await buttons.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) {
    const b = buttons.nth(i);
    expect((await b.innerText()).trim()).toBe("");
    await expect(b.locator("svg")).toHaveCount(1);
    expect(await b.getAttribute("title")).toBe(await b.getAttribute("aria-label"));
  }
}

/** Open a tab of the Index from the outline, switching it to Stories and unfolding its Index first (spec
 * 2026-10-16-outline-and-causes §1.2). */
export async function openIndex(page: Page, tab: "CLs" | "Files" | "Findings" | "Map") {
  const outline = page.locator("aside.ws-outline");
  const stories = outline.getByRole("button", { name: "Stories" });
  if ((await stories.getAttribute("aria-pressed")) !== "true") await stories.click();
  const index = outline.locator("details.ws-index");
  if (!(await index.evaluate((el) => (el as HTMLDetailsElement).open))) await index.locator("summary").click();
  await index.getByRole("link", { name: `Open the Index: ${tab}` }).click();
}

/** Pick an item of the first Explain ▾ (or Summarise ▾) menu inside `scope` (spec 2026-10-25-review-ui-redesign §4.1). */
export async function explainItem(scope: Locator, item: string | RegExp) {
  await scope.getByRole("button", { name: /^(Explain|Summarise)$/ }).first().click();
  await scope.getByRole("menuitem", typeof item === "string" ? { name: item, exact: true } : { name: item }).click();
}

/** Open the header's ⋯ menu (spec 2026-10-25-review-ui-redesign §2.2) unless it is open; returns the menu. */
export async function reviewMenu(page: Page): Promise<Locator> {
  const menu = page.getByRole("menu", { name: "Review menu" });
  if (!(await menu.isVisible())) await page.getByRole("button", { name: /^Review menu/ }).click();
  await expect(menu).toBeVisible();
  return menu;
}

/** Turn the ⋯ menu's Single-key shortcuts on or off (owner decision 2, 2026-10-26) by a pick, as a reader does; a menu that already
 * shows the wanted state is left with Escape. Returns once the menu has closed, with focus on ⋯. */
export async function setShortcuts(page: Page, on: boolean) {
  const menu = await reviewMenu(page), item = menu.getByRole("menuitemcheckbox", { name: "Single-key shortcuts" });
  await expect(item).toBeVisible();
  if ((await item.getAttribute("aria-checked")) === String(on)) await page.keyboard.press("Escape");
  else await item.click();
  await expect(menu).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Review menu/ })).toBeFocused();
}

/** What a polite live region holds each time it changes, from the call on; returns a function that reads the record. A screen reader
 * announces text put into a live region, so the same words are heard twice only if the region was emptied in between. */
export async function recordSaid(region: Locator): Promise<() => Promise<string[]>> {
  await region.evaluate((el) => {
    const log: string[] = [];
    (window as unknown as { said: string[] }).said = log;
    new MutationObserver(() => log.push(el.textContent ?? "")).observe(el, { childList: true, characterData: true, subtree: true });
  });
  return () => region.page().evaluate(() => (window as unknown as { said: string[] }).said);
}

/** Open the AI usage panel from the review menu; returns the panel. */
export async function openAiUsage(page: Page): Promise<Locator> {
  await (await reviewMenu(page)).getByRole("menuitem", { name: /^AI calls used · / }).click();
  const usage = page.getByRole("dialog", { name: "AI usage" });
  await expect(usage).toBeVisible();
  return usage;
}
