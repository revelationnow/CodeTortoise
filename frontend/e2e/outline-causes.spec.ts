import { devices, expect, type Page, test } from "@playwright/test";
import { barNames, expectNamed, expectNoNodeIds, hold, reviewMenu, startReview, storyLink } from "./helpers";

/** The outline and checks by cause (spec 2026-10-16-outline-and-causes): fixture CLs 101–104 make three threads; with
 * Confirm hidden their causes are a caller, a result and a reader in thread A and an ask in thread C. */
const FOUR = "101 102 103 104";

/** The reading as a review stored before causes, as the server sends it: the review's reading is validated on its way
 * out, so it carries `causes: null` and `cause: null` on each check; a story's reading is its raw stored blob, with
 * neither. */
async function withoutCauses(page: Page) {
  const strip = (served: "validated" | "raw") => async (route: import("@playwright/test").Route) => {
    let res: import("@playwright/test").APIResponse, j: any;
    try { res = await route.fetch(); j = await res.json(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    const r = j.reading ?? j;
    if (r && typeof r === "object") {
      if (served === "validated") { r.causes = null; for (const k of [...r.checks ?? [], ...r.cleared ?? []]) k.cause = null; }
      else { delete r.causes; for (const k of r.checks ?? []) delete k.cause; }
    }
    await route.fulfill({ response: res, json: j });
  };
  await page.route("**/api/reviews/*/reading", strip("validated"));
  await page.route("**/api/reviews/*/stories/*", strip("raw"));
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("while the reading loads, nothing of the layout before it shows; the reading is asked for first", async ({ page }) => {
    const base = await startReview(page);
    await page.addInitScript(() => {                    // anything of the old layout, however briefly it shows
      const w = window as unknown as { old: string[] };
      w.old = [];
      new MutationObserver(() => {
        if (document.querySelector("aside.ws-rail:not(.ws-outline):not(.folded)")) w.old.push("rail");
        if ([...document.querySelectorAll(".ws-head .bd-pill")].some((e) => /RISK$/.test(e.textContent ?? ""))) w.old.push("risk pill");
        if (document.querySelector(".ws-story-head:not(.st-head)")) w.old.push("story header");
      }).observe(document, { subtree: true, childList: true });
    });
    const asked: string[] = [];
    page.on("request", (r) => { const m = new URL(r.url()).pathname.match(/^\/api\/reviews\/\d+\/(\w+)$/); if (m) asked.push(m[1]); });
    let release = () => {};
    await page.route("**/api/reviews/*/reading", async (route) => { await new Promise<void>((r) => { release = r; }); await route.continue(); });
    for (const at of [base, `${base}/s/S1`]) {
      await page.goto(at);
      await expect(page.locator(".ws-centre")).toContainText("Loading");
      await expect(page.getByRole("complementary", { name: "Review contents" })).toContainText("Loading");
      await page.waitForTimeout(1000);                  // everything else has come; the reading is held back
      release();
      await expect(page.locator(".ws-outline").getByRole("button", { name: /^Thread A:/ })).toBeVisible();
      expect(await page.evaluate(() => (window as unknown as { old: string[] }).old)).toEqual([]);
    }
    expect(asked.indexOf("reading")).toBeGreaterThan(-1);
    expect(asked.indexOf("reading")).toBeLessThan(asked.indexOf("names"));
    expect(asked.indexOf("reading")).toBeLessThan(asked.indexOf("files"));
  });

  test("the outline comes back scrolled where the reader left it, though it shows before the reading", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 300 });          // short, so the outline scrolls
    const base = await startReview(page, FOUR);
    await page.locator("aside.ws-outline").getByRole("button", { name: /^Thread A:/ }).click();   // kept, so it reopens
    const box = page.locator("aside.ws-outline .ws-rail-scroll");
    expect(await box.evaluate((e) => e.scrollHeight - e.clientHeight)).toBeGreaterThan(40);
    const want = await box.evaluate((e) => new Promise<number>((done) => {     // halfway down, once the outline saved it
      e.addEventListener("scroll", () => done(e.scrollTop), { once: true });
      e.scrollTop = Math.floor((e.scrollHeight - e.clientHeight) / 2);
    }));
    const reading = await hold(page, "**/api/reviews/*/reading");
    await page.goto(base);
    await expect(page.getByRole("complementary", { name: "Review contents" })).toContainText("Loading");
    await reading.held;
    reading.release();
    await expect(page.locator(".ws-outline").getByRole("link", { name: /^Go to story S1/ })).toBeVisible();
    await expect.poll(() => box.evaluate((e) => e.scrollTop)).toBe(want);
  });

  test("a link to a story, or to a finding by its old address, never says it isn't in the review while its data loads", async ({ page }) => {
    const base = await startReview(page);
    await page.addInitScript(() => {                    // a false "missing", however briefly it shows
      const w = window as unknown as { said: string[] };
      w.said = [];
      new MutationObserver(() => {
        for (const e of document.querySelectorAll(".ws-centre .banner, .ws-crumbs, .ws-phonebar"))
          if (/isn't in this review|Not found/.test(e.textContent ?? "")) w.said.push((e.textContent ?? "").trim());
      }).observe(document, { subtree: true, childList: true, characterData: true });
    });
    for (const at of [`${base}/s/S1`, `${base}/f/F4`]) {
      const stories = await hold(page, "**/api/reviews/*/stories"), findings = await hold(page, "**/api/reviews/*/findings");
      const reading = page.waitForResponse((r) => /\/api\/reviews\/\d+\/reading$/.test(new URL(r.url()).pathname));
      await page.goto(at);
      await reading;
      await page.waitForTimeout(500);                   // the reading is in and drawn; what the place needs is held back
      await expect(page.locator(".ws-centre")).toContainText("Loading");
      stories.release();
      findings.release();
      await expect(page.locator(".ws-centre h2").first()).toBeVisible();
      expect(await page.evaluate(() => (window as unknown as { said: string[] }).said), at).toEqual([]);
    }
  });

  test("the outline's Stories: threads with open causes, the current story's flows", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await expect(outline.getByRole("button", { name: "Stories" })).toHaveAttribute("aria-pressed", "true");
    await expect.poll(() => barNames(page)).toEqual(["Thread A: hal_write in hal, 3 open, 0 of 2 read",
      "Thread B: logger_init in service, 0 of 2 read", "Thread C: svc::Engine::step in cpp, 1 open, 0 of 1 read"]);
    await (await storyLink(page, /^Go to story S1/)).click();
    const flows = outline.getByRole("link", { name: /^Go to flow / });
    await expect(flows.first()).toBeVisible();
    await flows.first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1\\?flow=1$`));
    await expect(outline.locator("details.ws-index")).not.toHaveAttribute("open");
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("the outline's Checks: causes by thread and story, Confirm hidden until shown, both remembered", async ({ page }) => {
    await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await expect(outline.locator(".ws-thread h3")).toHaveText(["A · hal_write in hal", "C · svc::Engine::step in cpp"]);
    const rows = outline.locator(".ws-row.cause");
    expect((await rows.locator(".ck-tag").allInnerTexts()).sort())
      .toEqual(["Ask the author", "Caller not updated", "Result handled the old way", "Unchanged reader"]);
    await expect(rows.first().locator(".ws-cdone")).toHaveText("0/1");
    const hide = outline.locator("details.ws-hidden");
    await expect(hide.locator("summary")).toHaveText("Showing: all but Confirm · 2 hidden");
    await hide.locator("summary").click();
    await hide.getByLabel("Confirm").check();
    await expect(rows).toHaveCount(6);
    await expect(hide.locator("summary")).toHaveText("Showing all");
    await page.reload();
    await expect(outline.getByRole("button", { name: "Checks" })).toHaveAttribute("aria-pressed", "true");
    await expect(rows).toHaveCount(6);
    await outline.locator("details.ws-hidden summary").click();
    await outline.locator("details.ws-hidden").getByLabel("Confirm").uncheck();
    await expect(rows).toHaveCount(4);
    await rows.filter({ hasText: "uart_init calls hal_write" }).click();
    await expect(page).toHaveURL(/open=cause%3Ac[0-9a-f]{10}&at=1/);
    await expectNoNodeIds(page);
  });

  test("a review stored before causes still loads and says to re-run for its checks", async ({ page }) => {
    await withoutCauses(page);
    const base = await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await expect.poll(async () => (await barNames(page))[0]).toBe("Thread A: hal_write in hal, 0 of 2 read");
    await expect(page.locator("section.ov-sec").first().locator(".ov-n")).toHaveText([", 2 stories", ", — open", ", 0 read"]);
    await outline.getByRole("button", { name: "Checks" }).click();
    await expect(outline).toContainText("Re-run the review to group its checks.");
    await page.goto(`${base}?open=cause:c0123456789&at=1`);
    await expect(page.getByText("This check isn't in this review.")).toBeVisible();
  });
});

/** The large fixture (CLs 201 202): ten functions write each `…Dev::errors`, so each writer's readers are a cause of
 * five places in one unchanged file, whose text comes from the source API. */
const READERS = "5 places read UartDev::errors, which uart_a1 now writes";

test.describe("a cause of many places", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });

  async function openReaders(page: Page) {
    await startReview(page, "201 202");
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await outline.getByRole("link", { name: `Open check: ${READERS}` }).click();
    return page.getByRole("complementary", { name: `Check: ${READERS}` });
  }

  test("the stepper shows the change above each place; J, K and F step, and All look fine finishes it", async ({ page }) => {
    const panel = await openReaders(page);
    await expect(panel.locator(".cs-pos")).toHaveText("1 / 5");
    await expect(panel.locator(".ws-detail-name b")).toHaveAttribute("title", READERS.replaceAll("`", ""));
    const change = panel.getByRole("region", { name: "The change" });
    await expect(change.locator("h3")).toContainText("uart_a1");
    await expect(change.locator(".cs-diff .add", { hasText: "errors" }).first()).toBeVisible();
    const place = panel.getByRole("region", { name: "The place" });
    await expect(place.locator("h3")).toContainText("uart_d1");
    await expect(place.locator(".cs-code .at")).toContainText("errors");
    await page.keyboard.press("j");
    await expect(panel.locator(".cs-pos")).toHaveText("2 / 5");
    await expect(place.locator("h3")).toContainText("uart_d2");
    await page.keyboard.press("k");
    await expect(panel.locator(".cs-pos")).toHaveText("1 / 5");
    await page.keyboard.press("f");
    await expect(panel.locator(".cs-pos")).toHaveText("2 / 5");
    await expect(panel.locator(".cs-donecount")).toHaveText("1 done");
    const row = page.locator("aside.ws-outline").getByRole("link", { name: `Open check: ${READERS}` });
    await expect(row.locator(".ws-cdone")).toHaveText("1/5");
    await panel.getByRole("button", { name: "Comment" }).click();
    const box = panel.getByPlaceholder("Leave a comment…");
    await box.pressSequentially("jkf");                                   // letters while typing, not steps
    await expect(box).toHaveValue("jkf");
    await expect(panel.locator(".cs-pos")).toHaveText("2 / 5");
    await panel.getByRole("button", { name: "All look fine" }).click();
    await expect(panel.locator(".cs-done")).toHaveText("All 5 places done");
    await expect(row.locator(".ws-cdone")).toHaveText("✓");
    await expect(page).toHaveURL(/open=cause%3Ac[0-9a-f]{10}&at=2/);
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  /** Hold each Looks fine (one place's mark) until `release` runs, or fail it at once. */
  async function holdMarks(page: Page, how: "hold" | "fail") {
    let release = () => {};
    const held = new Promise<void>((done) => { release = done; });
    await page.route((u) => u.pathname.endsWith("/mark"), async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      if (how === "fail") return route.fulfill({ status: 500, json: { detail: "the store is busy" } });
      await held;
      await route.continue();
    });
    return () => release();
  }

  test("J and K wait while a Looks fine is on its way, so it cannot pull the reader back", async ({ page }) => {
    const release = await holdMarks(page, "hold");
    const panel = await openReaders(page);
    await expect(panel.locator(".cs-pos")).toHaveText("1 / 5");
    await page.keyboard.press("f");
    await expect(panel.getByRole("button", { name: "Looks fine & next" })).toBeDisabled();
    await page.keyboard.press("j");
    await page.keyboard.press("j");
    await page.waitForTimeout(300);                                      // the mark is held: nothing else moves
    expect(await panel.locator(".cs-pos").textContent()).toBe("1 / 5");
    release();
    await expect(panel.locator(".cs-pos")).toHaveText("2 / 5");
    await expect(panel.locator(".cs-donecount")).toHaveText("1 done");
  });

  test("a failed Looks fine's banner goes when the reader steps to another place", async ({ page }) => {
    await holdMarks(page, "fail");
    const panel = await openReaders(page);
    await expect(panel.locator(".cs-pos")).toHaveText("1 / 5");
    await page.keyboard.press("f");
    await expect(panel.locator(".banner.warn")).toContainText("the store is busy");
    await expect(panel.locator(".cs-pos")).toHaveText("1 / 5");
    await page.keyboard.press("j");
    await expect(panel.locator(".cs-pos")).toHaveText("2 / 5");
    await expect(panel.locator(".banner.warn")).toHaveCount(0);
  });

  test("a place whose file text cannot be fetched says so and keeps its actions", async ({ page }) => {
    await page.route("**/api/reviews/*/source**", (route) => route.abort());
    const panel = await openReaders(page);
    await expect(panel.getByRole("region", { name: "The place" })).toContainText("No code for this place.");
    await expect(panel.getByRole("button", { name: "Looks fine & next" })).toBeEnabled();
    await expect(panel.getByRole("region", { name: "The change" })).toBeVisible();
  });
});

test.describe("an unknown check", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("an address naming a check the review lacks says so and leads to the checks", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}?open=cause:cffffffffff&at=1`);
    const panel = page.getByRole("complementary", { name: "Check: not found" });
    await expect(panel).toContainText("This check isn't in this review.");
    await panel.getByRole("button", { name: "Show the checks" }).click();
    await expect(page.locator("aside.ws-outline").getByRole("button", { name: "Checks" })).toHaveAttribute("aria-pressed", "true");
  });
});

test.describe("the top bar", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("Next open check walks the open causes in reading order and wraps; the progress line counts them", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const r = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/reading`)).json() as { causes: { kind: string; text: string }[] };
    const lines = r.causes.filter((c) => c.kind !== "confirm").map((c) => c.text.replaceAll("`", ""));
    expect(lines).toHaveLength(4);
    await expect(page.locator(".ws-progress")).toHaveText("0 of 5 stories read · 4 checks open");
    const next = page.getByRole("link", { name: "Next open check" });
    for (const line of [...lines, lines[0]]) {
      await next.click();
      await expect(page.getByRole("complementary", { name: `Check: ${line}` })).toBeVisible();
    }
    await page.getByRole("button", { name: "Looks fine & next" }).click();
    await expect(page.locator(".ws-progress")).toHaveText("0 of 5 stories read · 3 checks open");
    for (let i = 0; i < 3; i++) {
      await next.click();
      await page.getByRole("button", { name: "All look fine" }).click();
      await expect(page.locator(".cs-done")).toBeVisible();
    }
    await expect(next).toHaveCount(0);
    await expect(page.locator(".ws-progress")).toHaveText("0 of 5 stories read · every check done");
  });

  test("with every kind hidden there is no Next open check and nothing counted open", async ({ page }) => {
    await startReview(page, FOUR);
    await page.evaluate(() => window.localStorage.setItem("ct.ws.hiddenKinds", JSON.stringify(
      ["hazard", "confirm", "caller", "result", "reader", "target", "untested", "unanalysed", "ask"])));
    await page.reload();
    await expect(page.locator(".ws-progress")).toHaveText("0 of 5 stories read");
    await expect(page.getByRole("link", { name: "Next open check" })).toHaveCount(0);
  });

  test("the review menu opens how to read the page; Escape closes it and returns to the menu", async ({ page }) => {
    await startReview(page, FOUR);
    await (await reviewMenu(page)).getByRole("menuitem", { name: "How to read this page" }).click();
    const dialog = page.getByRole("dialog", { name: "How to read this page" });
    await expect(dialog).toContainText("J next, K back, F looks fine & next");
    await expect(dialog).toContainText("A faint violet line at the left of a paragraph marks text the AI wrote.");
    for (const w of [1440, 600]) {
      await page.setViewportSize({ width: w, height: 900 });
      await expect(dialog).toBeVisible();
      const seen = await dialog.evaluate((el) => {
        const b = el.getBoundingClientRect();
        const top = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
        return { inside: b.left >= 0 && b.top >= 0 && b.right <= window.innerWidth && b.bottom <= window.innerHeight,
                 hit: !!top && el.contains(top) };
      });
      expect(seen).toEqual({ inside: true, hit: true });
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Review menu/ })).toBeFocused();
  });
});

test.describe("a story's tabs", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a header with its thread and neighbours, tabs in the address that Back returns through, chips that open checks", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S2`);
    await expect(page.locator(".st-crumb")).toHaveText(/^Thread A · story 1 of 2 · feeds: /);
    const tabs = page.getByRole("navigation", { name: "Story sections" });
    await expect(tabs.getByRole("link", { name: /^Flows/ })).toHaveAttribute("aria-current", "page");
    await tabs.getByRole("link", { name: /^Where/ }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?sec=where$`));
    await expect(page.getByRole("region", { name: "Where" })).toBeVisible();
    await tabs.getByRole("link", { name: /^Call paths/ }).click();
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?sec=where$`));
    await tabs.getByRole("link", { name: "Graph" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?view=graph$`));
    await expect(page.locator(".bd-node").first()).toBeVisible();
    await page.goto(`${base}/s/S1`);
    const cards = page.getByRole("region", { name: /^Flow \d+:/ });
    await expect(cards.first()).toBeVisible();
    const chips = page.locator(".st-chip");
    expect(await chips.count()).toBeGreaterThan(0);
    const name = (await chips.first().getAttribute("aria-label"))!;
    await chips.first().click();
    await expect(page.getByRole("complementary", { name: name.replace("Open check: ", "Check: ") })).toBeVisible();
    await expectNoNodeIds(page);
    await expectNamed(page);
  });

  test("an outline flow line opens its card; a story remembers its tab; an old ?view=graph opens Graph", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await (await storyLink(page, /^Go to story S1/)).click();
    await outline.getByRole("link", { name: /^Go to flow 1:/ }).click();
    await expect(page.getByRole("region", { name: /^Flow 1:/ })).toHaveClass(/\blit\b/);
    await expect(page.getByRole("region", { name: /^Flow 1:/ })).toBeInViewport();
    await page.getByRole("navigation", { name: "Story sections" }).getByRole("link", { name: /^Code/ }).click();
    await outline.getByRole("link", { name: /^Go to story S2/ }).click();
    await outline.getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page).toHaveURL(/\/s\/S1\?sec=code/);
    await page.goto(`${base}/s/S2?view=graph`);
    await expect(page.getByRole("navigation", { name: "Story sections" }).getByRole("link", { name: "Graph" })).toHaveAttribute("aria-current", "page");
  });

  test("with every kind hidden a story shows no chips", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.evaluate(() => window.localStorage.setItem("ct.ws.hiddenKinds", JSON.stringify(
      ["hazard", "confirm", "caller", "result", "reader", "target", "untested", "unanalysed", "ask"])));
    await page.goto(`${base}/s/S1`);
    await expect(page.getByRole("region", { name: /^Flow 1:/ })).toBeVisible();
    await expect(page.locator(".st-chip")).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Other checks in this story" })).toHaveCount(0);
  });

  test("a story stored before causes shows no chips", async ({ page }) => {
    await withoutCauses(page);
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    await expect(page.getByRole("region", { name: /^Flow 1:/ })).toBeVisible();
    await expect(page.locator(".st-chip")).toHaveCount(0);
  });

  /** Patch a story's reading JSON on its way to the page. */
  async function patchStory(page: Page, sid: string, edit: (j: any) => void) {
    await page.route(`**/api/reviews/*/stories/${sid}`, async (route) => {
      const res = await route.fetch(), j = await res.json();
      edit(j);
      await route.fulfill({ response: res, json: j });
    });
  }

  test("a very long check line ends in an ellipsis inside its flow card, the whole line on hover", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const long = "`uart_send` changed so that " + "every caller that passed the old value now sees something else ".repeat(8);
    await patchStory(page, "S1", (j) => { for (const c of j.reading.causes) c.text = long; });
    await page.setViewportSize({ width: 700, height: 900 });
    await page.goto(`${base}/s/S1`);
    const chip = page.locator(".st-chip").first();
    await expect(chip).toBeVisible();
    const card = chip.locator("xpath=ancestor::section[1]");
    const [c, k] = [await chip.boundingBox(), await card.boundingBox()];
    expect(c!.x + c!.width).toBeLessThanOrEqual(k!.x + k!.width + 1);
    await expect(chip).toHaveAttribute("title", /every caller that passed/);
  });

  test("a flow whose account section was dropped shows its own text, not the next flow's section", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await patchStory(page, "S1", (j) => {
      const fl = j.board.flows.filter((f: any) => j.story.flows.includes(f.id));
      j.reading.account = [{ kind: "flow", heading: fl[1].text, text: "SECOND-FLOW-ACCOUNT", cites: [] }];
    });
    await page.goto(`${base}/s/S1`);
    await expect(page.getByRole("region", { name: /^Flow 2:/ })).toContainText("SECOND-FLOW-ACCOUNT");
    await expect(page.getByRole("region", { name: /^Flow 1:/ })).not.toContainText("SECOND-FLOW-ACCOUNT");
  });

  test("a story without flows lists its checks at the end of its first tab", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await patchStory(page, "S3", (j) => {
      j.reading.causes = [{ id: "cfixture", kind: "caller", thread: null, story: "S3", text: "a caller of `uart_send` now sees a new value",
                            places: [], flows: [], finding: null, change: null }];
    });
    await page.goto(`${base}/s/S3`);
    const region = page.getByRole("region", { name: "Checks in this story" });
    await expect(region.locator(".st-chip")).toHaveCount(1);
    await expect(page.getByRole("region", { name: /^Flow \d+:/ })).toHaveCount(0);
  });
});

test.describe("the overview", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the change, Start with Thread A then Continue, a section per thread and how they connect; nothing pinned beside it", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(base);
    await expect(page.locator(".ov3 h2")).toHaveText(["3 threads", "Build impact · up to 4 files rebuild", "Coverage · 2 notes",
                                                      "Discussion · no comments yet"]);
    const a = page.getByRole("region", { name: "Thread A: hal_write in hal" });
    await expect(a.locator(".ov-n")).toHaveText([", 2 stories", ", 3 open", ", 0 read"]);
    const intro = a.locator(".ov-intro");
    const full = (await intro.getAttribute("title")) ?? "";
    expect(full.length).toBeGreaterThan(0);
    expect(full).toContain(((await intro.innerText()).split("\n")[0] ?? "").slice(0, 20));
    expect(full).not.toMatch(/\bN\d+\b/);
    await expect(page.locator(".ov-links li")).toHaveText(["With Thread A: both run inside main",
                                                           "With Thread B: nothing besides arriving in CL 104 — ask the author"]);
    await expect(page.getByRole("region", { name: "Coverage" })).toContainText("Risks judged by rules only.");
    await expect(page.locator(".ov-howto, .ck-tile, .ov-progress, .ov-route, .ov2-check, .ov-thread, .ov-meta, .ov-conn-rows"))
      .toHaveCount(0);
    await page.getByRole("link", { name: "Start with Thread A ›" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2`));
    await page.getByRole("button", { name: "Mark as read" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1`));
    await page.goto(base);
    await expect(a.locator(".ov-n")).toHaveText([", 2 stories", ", 3 open", ", 1 read"]);
    await expect(a.getByRole("link", { name: "Continue thread A" })).toBeVisible();
    await page.getByRole("link", { name: "Continue ›", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1`));
    await page.goto(base);
    await page.getByRole("link", { name: "Start thread B" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S3`));
    await expectNoNodeIds(page);
    await expectNamed(page);
  });
});

test.describe("old links", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("?check= and an old finding address open the stepper at that check; /i/checks the outline's Checks", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const id = base.split("/")[2];
    const r = await (await page.request.get(`/api/reviews/${id}/reading`)).json() as
      { checks: { key: string; text: string; finding: string | null }[] };
    const caller = r.checks.find((k) => k.text.startsWith("`uart_init` calls"))!;
    await page.goto(`${base}/s/S2?check=${encodeURIComponent(caller.key)}`);
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?open=cause%3Ac[0-9a-f]{10}&at=1$`));
    await expect(page.getByRole("complementary", { name: /^Check: uart_init calls hal_write/ })).toBeVisible();
    const sig = r.checks.find((k) => k.text === "hal_write: signature changed")!;
    await page.goto(`${base}/f/${sig.finding}`);
    await expect(page.getByRole("complementary", { name: "Check: hal_write: signature changed" })).toBeVisible();
    await page.goto(`${base}/i/checks`);
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await expect(page.locator("aside.ws-outline").getByRole("button", { name: "Checks" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".ws-rail .ck-tile, .ov2-check, .ws-strip.right")).toHaveCount(0);
  });
});

test.describe("tablet", () => {
  test.use({ viewport: { width: 900, height: 1100 } });

  test("the outline is the drawer, with its switch", async ({ page }) => {
    await startReview(page, FOUR);
    await page.getByRole("button", { name: "Review contents" }).click();
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await outline.getByRole("link", { name: /^Open check: uart_init calls hal_write/ }).click();
    await expect(page.getByRole("complementary", { name: /^Check: uart_init calls hal_write/ })).toBeVisible();
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the stepper is a full-screen sheet that steps and marks; nothing scrolls sideways", async ({ page }) => {
    await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await outline.getByRole("link", { name: /^Open check: logger_flush ignores the result/ }).click();
    const sheet = page.getByRole("complementary", { name: /^Check: logger_flush ignores the result/ });
    await expect(sheet.getByRole("region", { name: "The place" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await sheet.getByRole("button", { name: "Looks fine & next" }).click();
    await expect(sheet.locator(".cs-done")).toHaveText("Its place is done");
    await sheet.getByRole("link", { name: "Close the check" }).click();
    await expect(sheet).toHaveCount(0);
  });
});

test.describe("names, never node ids", () => {
  test.use({ baseURL: "http://127.0.0.1:8795", viewport: { width: 1440, height: 900 } });

  test("a hazard whose AI reason cites nodes reads their names in the outline, the chips and the stepper", async ({ page }) => {
    const base = await startReview(page);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await expectNoNodeIds(page);
    await outline.locator(".ws-row.cause", { has: page.locator(".ck-tag.hazard") }).first().click();
    await expect(page.locator(".cs")).toBeVisible();
    await expectNoNodeIds(page);
    await page.goto(`${base}/s/S1`);
    await expect(page.locator(".st-chip.hazard").first()).toBeVisible();
    await expectNoNodeIds(page);
  });
});
