import { type APIResponse, devices, expect, type Locator, type Page, test } from "@playwright/test";
import { barNames, expectNamed, expectNoNodeIds, openFold, startReview } from "./helpers";

/** The overview's thread sections (spec 2026-10-25-review-ui-redesign §5): fixture CLs 101–104 make three threads, the
 * first two joined by a shared caller, the third only by arriving in CL 104. */
const FOUR = "101 102 103 104";

/** Serves the review's reading with `edit` applied, every time the page asks for it. */
async function patchReading(page: Page, edit: (r: any) => void) {
  await page.route("**/api/reviews/*/reading", async (route) => {
    let res: APIResponse, j: any;
    try { res = await route.fetch(); j = await res.json(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    edit(j);
    await route.fulfill({ response: res, json: j });
  });
}

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
  expect.soft(await page.locator(".ws-page").evaluate((e) => e.scrollWidth - e.clientWidth), "the page scrolls sideways")
    .toBeLessThanOrEqual(0);
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
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
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
