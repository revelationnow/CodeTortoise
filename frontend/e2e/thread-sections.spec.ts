import { type APIResponse, devices, expect, type Locator, type Page, test } from "@playwright/test";
import { barNames, expectNamed, expectNoNodeIds, LARGE, openFold, sideways, SINKS, startReview } from "./helpers";

/** The overview's thread sections (spec 2026-10-25-review-ui-redesign §5): fixture CLs 101–104 make three threads, the
 * first two joined by a shared caller, the third only by arriving in CL 104. */
const FOUR = "101 102 103 104";

/** Serves the review's reading or its stories with `edit` applied, every time the page asks for them. */
async function patchServed(page: Page, what: "reading" | "stories", edit: (j: any) => void) {
  await page.route(`**/api/reviews/*/${what}`, async (route) => {
    let res: APIResponse, j: any;
    try { res = await route.fetch(); j = await res.json(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    edit(j);
    await route.fulfill({ response: res, json: j });
  });
}
const patchReading = (page: Page, edit: (r: any) => void) => patchServed(page, "reading", edit);
const patchStories = (page: Page, edit: (s: any) => void) => patchServed(page, "stories", edit);

/** An element's right edge, to the pixel. */
const right = async (l: Locator) => { const b = (await l.boundingBox())!; return Math.round(b.x + b.width); };

/** Each thread bar measured in the page: how wide its name is, whether its Start/Continue stays inside its section, and
 * how many of its counts the "Thread X" label runs into. */
const bars = (page: Page) => page.locator("section.ov-sec").evaluateAll((secs) => secs.map((sec) => {
  const box = (sel: string) => sec.querySelector(sel)!.getBoundingClientRect();
  const section = sec.getBoundingClientRect(), label = box(".ov-sec-l"), act = box(".ov-act");
  const hit = (c: DOMRect) => c.left < label.right - 1 && c.right > label.left + 1 && c.top < label.bottom - 1 && c.bottom > label.top + 1;
  return { name: box(".ov-sec-name").width, actInside: act.right <= section.right + 1,
           overCounts: Array.from(sec.querySelectorAll(".ov-n")).filter((n) => hit(n.getBoundingClientRect())).length };
}));

/** The overview is narrower than `under` px because a panel is open beside it, whatever the window's width: its bars
 * still hold every name and their action, the label row is gone, and nothing sticks out or scrolls sideways (spec §5.2:
 * "below 640px wide" is the overview's own width). */
async function barsHold(page: Page, under: number) {
  await expect.poll(async () => (await page.locator(".ov3").boundingBox())!.width).toBeLessThan(under);
  await expect.soft(page.locator(".ov-cols")).toBeHidden();
  const found = await bars(page);
  expect(found).toHaveLength(3);
  found.forEach((b, i) => {
    expect.soft(b.name, `thread ${i + 1}: its name has room`).toBeGreaterThan(0);
    expect.soft(b.actInside, `thread ${i + 1}: its Start stays inside its section`).toBe(true);
    expect.soft(b.overCounts, `thread ${i + 1}: its label runs into its counts`).toBe(0);
  });
  expect.soft(await sideways(page), "the page scrolls sideways").toBeLessThanOrEqual(0);
}

/** Tab onto every row of the outline, from the overview link to the last link of the opened Index, then Shift+Tab back: none has any
 * of it under a bar (WCAG 2.2, 2.4.11) or outside the outline's box, whether it belongs to the open thread (between the bars pinned
 * above and below it) or follows the bars (the Tests group, the Index: under the bars pinned above them).
 * The outline must be short enough that the open thread cannot show whole between its bars, or this would prove nothing. */
async function focusStaysClear(page: Page) {
  const rail = page.locator("aside.ws-outline"), scroller = rail.locator(".ws-rail-scroll"), index = rail.locator("details.ws-index");
  await expect(rail.locator(".ws-bar-list a").first()).toBeVisible();
  if (!(await index.evaluate((el) => (el as HTMLDetailsElement).open))) await index.locator("summary").click();   // its summary and links are rows too
  await expect(index.locator("a")).toHaveCount(4);
  await expect(rail.locator(".ws-group a"), "the Tests rows are there to walk").not.toHaveCount(0);
  const room = await scroller.evaluate((box) => ({
    scrolls: box.scrollHeight > box.clientHeight, list: box.querySelector(".ws-bar-list")!.getBoundingClientRect().height,
    between: box.clientHeight - box.querySelectorAll(":scope > .ws-bar").length * 36,       // what is left of it when every bar is pinned
  }));
  expect(room.scrolls, "the outline scrolls").toBe(true);
  expect(room.list, "the thread is taller than the room between its bars").toBeGreaterThan(room.between);
  const clearance = () => page.evaluate(() => {
    const box = document.querySelector(".ws-rail-scroll")!, edge = box.getBoundingClientRect();
    const el = document.activeElement!, row = el.getBoundingClientRect(), isBar = !!el.closest(".ws-bar");   // a bar is never under another: the later ones paint over the earlier
    const under = Array.from(box.querySelectorAll(":scope > .ws-bar")).map((b) => {
      const r = b.getBoundingClientRect();
      return Math.min(row.bottom, r.bottom) - Math.max(row.top, r.top);
    });
    return { name: el.getAttribute("aria-label") ?? el.textContent?.trim(), inBox: box.contains(el),
             under: isBar ? 0 : Math.max(0, ...under), out: isBar ? 0 : Math.max(0, edge.top - row.top, row.bottom - edge.bottom) };
  });
  // A pixel of slack: the bars sit on whole device pixels and the rows on fractions of one, so a row clear of a bar still overlaps it by up
  // to half a pixel (measured, at several stops); the bar's own bottom border is 1px.
  const slack = 1;
  const stop = async (how: string) => {
    const c = await clearance();
    expect.soft(c.inBox, `${how} stays in the outline`).toBe(true);
    expect.soft(c.under, `${how}, ${c.name}: px under a pinned bar`).toBeLessThanOrEqual(slack);
    expect.soft(c.out, `${how}, ${c.name}: px outside the outline's box`).toBeLessThanOrEqual(slack);
  };
  const rows = scroller.locator("a:visible, button:visible, summary:visible"), n = await rows.count();
  await rows.first().focus();
  await stop("focus");
  for (let i = 1; i < n; i++) { await page.keyboard.press("Tab"); await stop(`Tab to row ${i + 1} of ${n}`); }
  for (let i = n - 1; i > 0; i--) { await page.keyboard.press("Shift+Tab"); await stop(`Shift+Tab to row ${i} of ${n}`); }
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("each thread is a section headed Thread A, B, C, its counts lined up under Stories, Open and Read", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(base);
    await expect(page.locator(".ov3 h2").first()).toHaveText("3 threads");
    await expect(page.getByRole("link", { name: "Start with Thread A ›" })).toBeVisible();
    const secs = page.locator("section.ov-sec");
    await expect(secs).toHaveCount(3);
    expect(await secs.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label"))))
      .toEqual(["Thread A: hal_write in hal", "Thread B: logger_init in service", "Thread C: svc::Engine::step in cpp"]);
    await expect(secs.nth(0).locator(".ov-n")).toHaveText([", 2 stories", ", 3 open", ", 0 read"]);
    await expect(secs.nth(1).locator(".ov-n")).toHaveText([", 2 stories", ", 0 open", ", 0 read"]);
    await expect(secs.nth(2).locator(".ov-n")).toHaveText([", 1 story", ", 1 open", ", 0 read"]);
    const labels = page.locator(".ov-cols > span");
    await expect(labels).toHaveText(["", "Stories", "Open", "Read", ""]);
    for (let s = 0; s < 3; s++)
      for (let c = 0; c < 3; c++)
        expect(Math.abs(await right(secs.nth(s).locator(".ov-n").nth(c)) - await right(labels.nth(c + 1))), `section ${s}, column ${c}`)
          .toBeLessThanOrEqual(1);
    await expect(secs.nth(0).locator(".ov-links")).toHaveCount(0);
    await expect(secs.nth(1).locator(".ov-links li")).toHaveText(["With Thread A: both run inside main"]);
    await expect(secs.nth(2).locator(".ov-links li")).toHaveText(["With Thread B: nothing besides arriving in CL 104 — ask the author"]);
    await expectNoNodeIds(page);
    await expectNamed(page);
    await secs.nth(1).getByRole("link", { name: "Start thread B" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S3$`));
    await page.getByRole("button", { name: "Mark as read" }).click();
    await page.goto(base);
    await expect(secs.nth(1).locator(".ov-n").last()).toHaveText(", 1 read");
    await expect(page.getByRole("link", { name: "Continue ›", exact: true })).toBeVisible();
    await secs.nth(1).getByRole("link", { name: "Continue thread B" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S5$`));
    expect((await page.request.put(`/api/reviews/${base.split("/")[2]}/ticks/story/S5`)).ok()).toBe(true);
    await page.goto(base);
    await expect(secs.nth(1).locator(".ov-act")).toHaveText("All read ✓");
  });

  test("a connection line the strong model reworded carries the AI edge on its words alone, not on the thread it names or the author note", async ({ page }) => {
    // the AI fixtures' stub never rewords a connection, so the reading is served as if the strong model had
    await patchReading(page, (r) => { for (const k of r.connections) k.text_source = "llm"; });
    const base = await startReview(page, FOUR);
    await page.goto(base);
    const line = (n: number) => page.locator("section.ov-sec").nth(n).locator(".ov-links li");
    await expect(line(1)).toHaveText("With Thread A: Written by AI. both run inside main");
    await expect(line(2)).toHaveText("With Thread B: Written by AI. nothing besides arriving in CL 104 — ask the author");
    for (const n of [1, 2]) {
      const words = line(n).locator(".ai-text");
      await expect(words).toHaveCount(1);
      await expect(words).toHaveAttribute("title", "Written by AI");
      await expect(words).not.toContainText(/With Thread|ask the author/);
    }
    await expect(line(1).locator(".ai-text")).toHaveText("Written by AI. both run inside main");
    await expect(line(2).locator(".ai-text")).toHaveText("Written by AI. nothing besides arriving in CL 104");
  });

  test("a reworded connection's words begin on the line of their prefix, and the edge runs beside every line they wrap to", async ({ page }) => {
    const long = "both start up from `main` once the driver is brought up and the logger is ready to take its first line, ".repeat(4);
    await patchReading(page, (r) => { r.connections[0].text_source = "llm"; r.connections[0].text = long.trim(); });
    const base = await startReview(page, FOUR);
    await page.goto(base);
    const line = page.locator("section.ov-sec").nth(1).locator(".ov-links li");
    await expect(line.locator(".ai-text")).toHaveCount(1);
    const m = await line.evaluate((li) => {
      const span = li.querySelector(".ai-text")!, range = document.createRange(), box = (r: DOMRect) => ({ top: r.top, bottom: r.bottom, left: r.left });
      range.selectNodeContents(li.firstChild!);                                       // "With Thread A: ", the text before the words
      const prefix = box(range.getClientRects()[0]);
      const texts: DOMRect[] = [];                                                    // each line of the words themselves, not the hidden "Written by AI."
      for (const walk = document.createTreeWalker(span, NodeFilter.SHOW_TEXT); walk.nextNode();) {
        if (walk.currentNode.parentElement!.closest(".vh")) continue;
        range.selectNodeContents(walk.currentNode);
        texts.push(...range.getClientRects());
      }
      const style = getComputedStyle(span);
      return {
        prefix,
        // a box per line the words are on; the words start this far in from its left side, which only an edge and its padding there account for
        lines: [...span.getClientRects()].map((f) => {
          const here = texts.filter((t) => (t.top + t.bottom) / 2 > f.top && (t.top + t.bottom) / 2 < f.bottom);
          return { ...box(f), texts: here.length, inset: Math.min(...here.map((t) => t.left)) - f.left };
        }),
        edge: { width: style.borderLeftWidth, style: style.borderLeftStyle, padding: style.paddingLeft,
                clone: style.getPropertyValue("box-decoration-break") || style.getPropertyValue("-webkit-box-decoration-break") },
      };
    });
    expect(m.lines.length, "the words wrap").toBeGreaterThan(1);
    expect(m.lines[0].top < m.prefix.bottom && m.lines[0].bottom > m.prefix.top, "the words begin on the line of With Thread A:, not below it").toBe(true);
    m.lines.forEach((l, i) => {
      expect(l.texts, `line ${i + 1} of the words holds some of them`).toBeGreaterThan(0);
      expect(l.inset, `line ${i + 1}: the words sit 12px in from its left side: the 2px edge and 10px of padding, drawn again on every line`).toBeGreaterThanOrEqual(11.5);
    });
    expect(m.edge, "the edge repeats on every line the words wrap to").toEqual({ width: "2px", style: "solid", padding: "10px", clone: "clone" });
  });

  test("a thread with more than four stories shows four, and the others in place", async ({ page }) => {
    await patchReading(page, (r) => { r.threads[0].stories = ["S2", "S1", "S3", "S5", "S4", "S9"]; });
    const base = await startReview(page, FOUR);
    await page.goto(base);
    const a = page.getByRole("region", { name: /^Thread A:/ });
    const items = a.locator(".ov-stories > li");
    await expect(items).toHaveCount(4);
    await expect(a.locator(".ov-n").first()).toHaveText(", 6 stories");
    const { causes } = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/reading`)).json() as
      { causes: { story: string | null; kind: string }[] };
    const opens = (sid: string) => causes.filter((c) => c.story === sid && c.kind !== "confirm").length;
    expect(opens("S2") + opens("S1")).toBe(3);                                       // the thread's 3 open, all on these two
    await expect(items.nth(0).locator(".ov-open")).toHaveText(`, ${opens("S2")} open`);
    await expect(items.nth(1).locator(".ov-open")).toHaveText(`, ${opens("S1")} open`);
    await expect(items.nth(0).getByRole("link")).toHaveAttribute("title", /\S/);   // the whole title on hover
    const more = a.getByRole("button", { name: "Show the other 2 stories ▸" });
    await expect(more).toHaveAttribute("aria-expanded", "false");
    await more.click();
    await expect(items).toHaveCount(6);
    await expect(items.last()).toHaveText("Story S9");                               // a story the review no longer has
    const fewer = a.getByRole("button", { name: "Show fewer ▴" });
    await expect(fewer).toHaveAttribute("aria-expanded", "true");
    await fewer.click();
    await expect(items).toHaveCount(4);
  });

  test("Build impact, Coverage and Discussion are folded rows whose headings say what they hold", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(base);
    await expect(page.locator(".ov3 h2")).toHaveText(["1 thread", "Build impact · up to 4 files rebuild", "Coverage · 2 notes",
                                                      "Discussion · no comments yet"]);
    const cov = page.getByRole("region", { name: "Coverage", exact: true });
    await expect(cov.getByText("Risks judged by rules only.")).toBeHidden();
    await openFold(page, "Coverage");
    await expect(cov.getByText("Risks judged by rules only.")).toBeVisible();
    await page.request.post(`/api/reviews/${base.split("/")[2]}/comments`,
                            { data: { body: "overall: please split the CLs", anchor_kind: "review", anchor: {} } });
    await page.reload();
    const talk = await openFold(page, "Discussion");
    await expect(talk.locator("h2")).toHaveText("Discussion · 1 comment");
    await expect(talk.getByText("overall: please split the CLs")).toBeVisible();
    await expectNamed(page);
  });

  test("a review with no threads says the change and starts here, with no column labels (review focus 2)", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await patchReading(page, (r) => { r.threads = []; r.connections = []; });
    await page.goto(base);
    await expect(page.locator(".ov3 h2").first()).toHaveText("The change");
    await expect(page.locator(".ov-cols, section.ov-sec")).toHaveCount(0);
    const top = (await page.locator(".ov-top").boundingBox())!, fold = (await page.locator(".ov3 > section:has(> details.ov-fold)").first().boundingBox())!;
    expect(fold.y - (top.y + top.height), "from the change to the first fold: a row's gap, as between the folds").toBeCloseTo(6, 0);
    await page.getByRole("link", { name: "Start here ›" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2$`));
  });

  test("the outline opens one thread at a time, keeps it per review, and pins the other bars to its top and bottom", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 320 });                      // short, so the outline scrolls
    const base = await startReview(page, FOUR);
    const rail = page.locator("aside.ws-outline"), box = rail.locator(".ws-rail-scroll");
    const bar = (L: string) => rail.getByRole("button", { name: new RegExp(`^Thread ${L}:`) });
    await expect.poll(() => barNames(page)).toEqual(["Thread A: hal_write in hal, 3 open, 0 of 2 read",
      "Thread B: logger_init in service, 0 of 2 read", "Thread C: svc::Engine::step in cpp, 1 open, 0 of 1 read"]);
    await expect(rail.locator(".ws-bar-list")).toHaveCount(0);                     // a fresh review opens none
    await expect(rail.getByRole("link", { name: "Go to the overview" })).toHaveText("⌂ Overview");   // the header has the risk
    await page.goto(`${base}/s/S3`);
    await expect(bar("B")).toHaveAttribute("aria-expanded", "true");               // the current story's thread
    await expect(bar("A")).toHaveAttribute("aria-expanded", "false");
    await expect(rail.locator(".ws-bar-list > li > .ws-row.story .ws-num")).toHaveText(["1", "2"]);
    const edges = async () => { const b = (await box.boundingBox())!; return { top: b.y, bottom: b.y + b.height }; };
    await box.evaluate((e) => { e.scrollTop = 0; });
    const c = (await bar("C").boundingBox())!;
    expect(Math.abs(c.y + c.height - (await edges()).bottom)).toBeLessThanOrEqual(1);   // C pinned at the bottom
    await box.evaluate((e) => { e.scrollTop = e.scrollHeight; });
    await expect.poll(async () => Math.round((await bar("A").boundingBox())!.y - (await edges()).top)).toBe(0);
    expect(Math.round((await bar("B").boundingBox())!.y - (await edges()).top)).toBe(36);   // A and B pinned at the top
    await bar("A").click();                                                       // another bar opens, the open one shuts
    await expect(bar("A")).toHaveAttribute("aria-expanded", "true");
    await expect(bar("B")).toHaveAttribute("aria-expanded", "false");
    await bar("A").click();                                                       // the open bar shuts
    await expect(rail.locator(".ws-bar-list")).toHaveCount(0);
    await bar("C").click();
    await page.goto(base);
    await expect(bar("C")).toHaveAttribute("aria-expanded", "true");               // kept for this review
    expect(await page.evaluate((k) => localStorage.getItem(k), `ct.ws.${base.split("/")[2]}.thread`)).toBe('"T3"');
    await page.goto(`${base}/s/S1`);
    await expect(bar("A")).toHaveAttribute("aria-expanded", "true");               // going to a story opens its thread
    await expect(bar("C")).toHaveAttribute("aria-expanded", "false");
    await expectNamed(page);
  });

  test("a narrow outline keeps the thread's name: under 240px a bar drops the word Thread, not its letter, name or caret", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("ct.ws.railW", "200"));     // dragged to its narrowest, before the page loads
    await startReview(page, FOUR);
    const rail = page.locator("aside.ws-outline"), bar = rail.locator(".ws-bar").first(), button = bar.locator("> button");
    await expect(button).toBeVisible();
    await page.addStyleTag({ content: ".ws-rail-scroll { scrollbar-gutter: stable; }" });   // a classic scrollbar takes 15px of the bar's room; headless Chromium draws none, so reserve the same gutter
    expect((await rail.boundingBox())!.width).toBe(200);
    await expect(bar.locator(".ws-bar-l")).toBeHidden();                              // the word goes…
    await expect(bar.locator(".ov-letter")).toBeVisible();                             // …the letter circle stays
    await expect(bar.locator(".ov-letter")).toHaveText("A");
    expect((await bar.locator(".ws-one").boundingBox())!.width, "the name has room").toBeGreaterThanOrEqual(40);
    const spill = () => button.evaluate((b) => b.querySelector(".ws-bar-caret")!.getBoundingClientRect().right
      - (b.getBoundingClientRect().right - parseFloat(getComputedStyle(b).paddingRight)));
    expect(await spill(), "the caret ends inside the bar, clear of its padding").toBeLessThanOrEqual(0.5);
    await expect(button).toHaveAttribute("title", "Thread A: hal_write in hal");      // the word is still said
    await expect(button).toHaveAttribute("aria-label", "Thread A: hal_write in hal, 3 open, 0 of 2 read");
    // "under 240px" is the outline's own width, the one the reader drags: 239 drops the word, 240 keeps it
    const grip = rail.locator(":scope > .bd-resizer"), width = async () => (await rail.boundingBox())!.width;
    const widen = async (dx: number) => {
      const g = (await grip.boundingBox())!, x = g.x + g.width / 2, y = g.y + g.height / 2;
      await page.mouse.move(x, y);
      await page.mouse.down();
      await page.mouse.move(x + dx, y, { steps: 4 });
      await page.mouse.up();
    };
    await widen(39);
    await expect.poll(width).toBe(239);
    await expect(bar.locator(".ws-bar-l")).toBeHidden();
    await widen(1);
    await expect.poll(width).toBe(240);
    await expect(bar.locator(".ws-bar-l")).toBeVisible();
    await expect(bar.locator(".ws-bar-l")).toHaveText("Thread A");
    expect(await spill()).toBeLessThanOrEqual(0.5);
  });

  test("the outline's fold button sits beside the Stories | Checks switch, not on it, from the default width down to the narrowest", async ({ page }) => {
    await startReview(page);
    const rail = page.locator("aside.ws-outline"), fold = rail.locator(":scope > .ws-fold"), seg = rail.locator(".ws-outline-switch");
    await expect(seg).toBeVisible();
    const apart = async (width: number) => {
      await expect.poll(async () => (await rail.boundingBox())!.width).toBe(width);
      const [r, f, s] = await Promise.all([rail, fold, seg].map(async (l) => (await l.boundingBox())!));
      const within = (b: typeof r) => b.x >= r.x && b.y >= r.y && b.x + b.width <= r.x + r.width && b.y + b.height <= r.y + r.height;
      const meet = f.x < s.x + s.width && s.x < f.x + f.width && f.y < s.y + s.height && s.y < f.y + f.height;
      expect(meet, `${width}px: the fold button (x ${f.x}–${f.x + f.width}) is clear of the switch (x ${s.x}–${s.x + s.width})`).toBe(false);
      expect(within(f), `${width}px: the fold button is inside the rail`).toBe(true);
      expect(within(s), `${width}px: the switch is inside the rail`).toBe(true);
      expect(await seg.locator("button").evaluateAll((bs) => bs.map((b) => b.scrollWidth <= b.clientWidth)), `${width}px: both labels fit`)
        .toEqual([true, true]);
    };
    await apart(280);                                                               // the default
    await page.evaluate(() => localStorage.setItem("ct.ws.railW", "200"));          // dragged to its narrowest
    await page.reload();
    await expect(seg).toBeVisible();
    await apart(200);
  });

  test("keyboard focus never hides under a pinned bar: Tab and Shift+Tab through the whole outline of a short window, the Tests rows and the Index too", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await patchStories(page, (s) => {                                              // the fixture has no Tests group: three rows after the bars
      for (let i = 1; i <= 3; i++) s.stories.push({ ...s.stories.at(-1), id: `S10${i}`, kind: "tests", title: `Tests of the Uart driver ${i}`, flows: [], nodes: [], findings: [] });
      for (let i = 1; i <= 3; i++) s.stories.push({ ...s.stories[0], id: `S20${i}`, title: `Another story of the service ${i}`, flows: [], nodes: [], findings: [] });
    });
    await patchReading(page, (r) => { r.threads[2].stories.push("S201", "S202", "S203"); });   // Thread C has one story: its list would fit between the three bars, and prove nothing there
    await page.setViewportSize({ width: 1440, height: 320 });                      // short, so the outline scrolls
    const base = await startReview(page, FOUR);
    const last = ((await (await page.request.get(`/api/reviews/${base.split("/")[2]}/reading`)).json()) as { threads: { stories: string[] }[] }).threads[2].stories[0];
    for (const [sid, lines] of [["S1", 2], ["S3", 0], [last, 0]] as const) {       // Thread A of three (a bar above its list, two below; S1 has two flow lines), Thread B (two above, one below), then C (the three bars above: 108px)
      await page.goto(`${base}/s/${sid}`);
      await expect(page.locator(".ws-bar-list a[aria-current='page']"), `${sid}: the open thread's list has drawn`).toBeVisible();
      await expect(page.getByRole("navigation", { name: "Story sections" }), `${sid}: the story is in, so its flow lines are`).toBeVisible();
      await expect(page.locator(".ws-bar-list .ws-flows a")).toHaveCount(lines);
      await focusStaysClear(page);
    }
    expect(errors).toEqual([]);
  });

  test("going back inside the app to a story opens its thread, not the bar clicked since", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const rail = page.locator("aside.ws-outline");
    const bar = (L: string) => rail.getByRole("button", { name: new RegExp(`^Thread ${L}:`) });
    await page.goto(`${base}/s/S3`);                                               // Thread B
    await expect(bar("B")).toHaveAttribute("aria-expanded", "true");
    await bar("A").click();                                                       // looking at A's stories while on S3…
    await expect(bar("A")).toHaveAttribute("aria-expanded", "true");
    await rail.getByRole("link", { name: /^Go to story S2/ }).click();            // …and going to one: no reload
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2$`));
    await expect(rail.getByRole("link", { name: /^Go to story S2/ })).toHaveAttribute("aria-current", "page"); // the URL moves first: S2 must be drawn before going back
    await expect(bar("A")).toHaveAttribute("aria-expanded", "true");
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S3$`));
    await expect(bar("B")).toHaveAttribute("aria-expanded", "true");               // back on S3: its thread, not the one clicked since
    await expect(bar("A")).toHaveAttribute("aria-expanded", "false");
    await expect(rail.getByRole("link", { name: /^Go to story S3/ })).toHaveAttribute("aria-current", "page");
  });

  test("on the overview the outline opens the thread last opened, not a bar clicked before going to a story", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const rail = page.locator("aside.ws-outline");
    const bar = (L: string) => rail.getByRole("button", { name: new RegExp(`^Thread ${L}:`) });
    await bar("C").click();                                                       // clicked on the overview…
    await expect(bar("C")).toHaveAttribute("aria-expanded", "true");
    await page.getByRole("region", { name: /^Thread B:/ }).getByRole("link", { name: "Start thread B" }).click();   // …then a story of B, no reload
    await expect(page).toHaveURL(new RegExp(`${base}/s/S3$`));
    await expect(bar("B")).toHaveAttribute("aria-expanded", "true");
    await rail.getByRole("link", { name: "Go to the overview" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await expect(rail.getByRole("link", { name: "Go to the overview" })).toHaveAttribute("aria-current", "page");   // drawn: the address changes first
    await expect(bar("B")).toHaveAttribute("aria-expanded", "true");               // the thread opened last is B, not the C clicked before
    await expect(bar("C")).toHaveAttribute("aria-expanded", "false");
  });

  test("stepping on to another story of the same thread makes that thread the last opened, not a bar clicked on the way", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const rail = page.locator("aside.ws-outline");
    const bar = (L: string) => rail.getByRole("button", { name: new RegExp(`^Thread ${L}:`) });
    await page.goto(`${base}/s/S3`);                                               // Thread B, story 1 of 2
    await expect(bar("B")).toHaveAttribute("aria-expanded", "true");
    await bar("A").click();                                                       // a look at A's stories, kept as the last opened…
    await expect(bar("A")).toHaveAttribute("aria-expanded", "true");
    await page.getByRole("link", { name: /^Next story: S5/ }).click();            // …then the story page's › to B's second story, no reload
    await expect(page).toHaveURL(new RegExp(`${base}/s/S5$`));
    await expect(bar("B")).toHaveAttribute("aria-expanded", "true");               // B holds S5
    await expect(bar("A")).toHaveAttribute("aria-expanded", "false");
    await rail.getByRole("link", { name: "Go to the overview" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await expect(rail.getByRole("link", { name: "Go to the overview" })).toHaveAttribute("aria-current", "page");   // drawn: the address changes first
    await expect(bar("B")).toHaveAttribute("aria-expanded", "true");               // the thread of the story the reader was on, not A
    await expect(bar("A")).toHaveAttribute("aria-expanded", "false");
    expect(await page.evaluate((k) => localStorage.getItem(k), `ct.ws.${base.split("/")[2]}.thread`)).toBe('"T2"');   // and kept so
  });
});

test.describe("a thread with many flow lines", () => {
  test.use({ baseURL: LARGE, viewport: { width: 1440, height: 320 } });

  test("keyboard focus never hides under the pinned bar while Tab and Shift+Tab walk a story's six flow lines, its Tests row and the Index", async ({ page }) => {
    const base = await startReview(page, "201 202");
    await page.goto(`${base}/s/S1`);                                               // the only thread, so one bar above its list and none below
    await expect(page.locator(".ws-bar-list .ws-flows a")).toHaveCount(6);
    await focusStaysClear(page);
  });
});

test.describe("shared sinks", () => {
  test.use({ baseURL: SINKS });

  test("Coverage stays open when Show or Hide on its sinks line loads the page again", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(base);
    const cov = await openFold(page, "Coverage"), fold = cov.locator("details.ov-fold");
    await cov.getByRole("button", { name: "Show" }).click();
    await expect(cov).toContainText(/shared sinks? shown/);                      // the page that loaded again…
    await expect(fold).toHaveAttribute("open", "");                              // …has Coverage open
    await expect(cov.getByRole("button", { name: "Hide" })).toBeVisible();
    await cov.getByRole("button", { name: "Hide" }).click();
    await expect(cov).toContainText(/shared sinks? hidden/);
    await expect(fold).toHaveAttribute("open", "");
    await expect(cov.getByRole("button", { name: "Show" })).toBeVisible();
    await page.goto(`${base}/s/S1`);                                             // a visit of its own to the overview: shut, as folds are
    await page.goto(base);
    await expect(fold).toBeVisible();
    await expect(fold).not.toHaveAttribute("open", "");
    // and by the app's own navigation, with no new document: open Coverage, follow a story, come back by the overview link
    await openFold(page, "Coverage");
    await page.locator(".ov-stories a").first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S\\d+$`));
    await page.getByRole("link", { name: "Go to the overview" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await expect(fold).toBeVisible();
    await expect(fold, "Coverage starts shut again").not.toHaveAttribute("open", "");
  });

  test.describe("on a phone", () => {
    test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
      deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

    test("the page that loads again is still the overview, Coverage open", async ({ page }) => {
      await startReview(page);                                                   // a phone opens on the contents: the overview is a page of its own
      await page.getByRole("link", { name: "Go to the overview" }).click();
      const cov = await openFold(page, "Coverage");
      await cov.getByRole("button", { name: "Show" }).click();
      await expect(cov).toContainText(/shared sinks? shown/);
      await expect(cov.locator("details.ov-fold")).toHaveAttribute("open", "");
      await expect(page.locator(".ov3 h2").first()).toHaveText("1 thread");
    });
  });
});

test.describe("beside the side panel", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("a panel open beside the overview narrows it: the thread bars wrap by its width and keep their names", async ({ page }) => {
    await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await outline.getByRole("link", { name: /^Open check: / }).first().click();
    const panel = page.getByRole("complementary", { name: /^Check: / });
    await expect(panel).toBeVisible();
    await expect(page.locator("section.ov-sec")).toHaveCount(3);          // the overview stays in the centre
    await barsHold(page, 640);
    await panel.getByRole("button", { name: "Focus" }).click();           // Focus leaves the centre 360px: the overview ~312
    await barsHold(page, 330);
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the counts wrap under the thread's name with their words, and nothing scrolls sideways", async ({ page }) => {
    await startReview(page, FOUR);
    await page.getByRole("link", { name: "Go to the overview" }).click();
    const a = page.getByRole("region", { name: /^Thread A:/ });
    await expect(a).toBeVisible();
    await expect(page.locator(".ov-cols")).toBeHidden();
    const name = (await a.locator("h3").boundingBox())!, counts = (await a.locator(".ov-counts").boundingBox())!;
    expect(counts.y).toBeGreaterThanOrEqual(name.y + name.height - 1);
    expect((await a.locator(".ov-w").first().boundingBox())!.width).toBeGreaterThan(10);   // "stories" shows
    await expect(a.locator(".ov-sep").first()).toBeVisible();
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });

  test("back on the contents page the outline opens the thread of the story just read, not the bar tapped before", async ({ page }) => {
    await startReview(page, FOUR);
    const rail = page.locator("aside.ws-outline");
    const bar = (L: string) => rail.getByRole("button", { name: new RegExp(`^Thread ${L}:`) });
    await bar("A").click();                                                       // tapped on the contents page…
    await expect(bar("A")).toHaveAttribute("aria-expanded", "true");
    await rail.getByRole("link", { name: "Go to the overview" }).click();         // …then the overview, with no outline beside it
    await page.getByRole("region", { name: /^Thread B:/ }).getByRole("link", { name: "Start thread B" }).click();   // and a story of B, no reload
    await expect(page).toHaveURL(/\/s\/S3$/);
    await expect(page.locator(".st-crumb")).toContainText("Thread B");            // drawn: the address changes first
    await page.getByRole("link", { name: "Back to Thread B" }).click();           // the phone bar's way back to the contents
    await expect(bar("B")).toHaveAttribute("aria-expanded", "true");
    await expect(bar("A")).toHaveAttribute("aria-expanded", "false");
  });
});
