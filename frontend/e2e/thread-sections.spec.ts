import { type APIResponse, devices, expect, type Locator, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, openFold, startReview } from "./helpers";

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
});
