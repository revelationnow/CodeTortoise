import { devices, expect, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, openIndex, startReview } from "./helpers";

/** A review read as threads (spec 2026-10-07-review-reading §5, §7, §13): fixture CLs 101–104 make three threads, the
 * first two joined by a shared caller, the third only by arriving in CL 104. */
const FOUR = "101 102 103 104";

/** Re-run the review and wait until the new run's reading is stored. */
async function rerun(page: Page, base: string) {
  const id = base.split("/")[2];
  const finished = async () => {
    const d = await (await page.request.get(`/api/reviews/${id}`)).json();
    return { status: d.review.status as string, at: d.stages.find((s: { name: string }) => s.name === "reading")?.finished_at as string };
  };
  const before = (await finished()).at;
  expect((await page.request.post(`/api/reviews/${id}/rerun`)).ok()).toBe(true);
  await expect.poll(async () => { const f = await finished(); return f.at !== before && ["done", "degraded"].includes(f.status); },
                    { timeout: 60_000 }).toBe(true);
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the overview tells the change as threads, how they connect and what to check", async ({ page }) => {
    await startReview(page, FOUR);
    await expect(page.locator(".ov3 h2")).toHaveText(["The change as a whole", "Threads", "How the threads connect", "Build impact",
                                                      "Coverage", "Discussion"]);
    await expect(page.locator(".ov3 .ws-lead")).toHaveText("3 threads: A and B: both run inside main; B and C: nothing besides arriving in CL 104.");
    await expect(page.locator(".ov-conn-rows li")).toHaveText(["A and B: both run inside main",
                                                               "B and C: nothing besides arriving in CL 104 — ask the author"]);
    const threads = page.locator(".ov-thread");
    await expect(threads.locator("h3")).toHaveText(["hal_write in hal", "logger_init in service", "svc::Engine::step in cpp"]);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await expect(outline.locator(".ws-thread h3")).toHaveText(["A · hal_write in hal", "C · svc::Engine::step in cpp"]);
    await outline.locator("details.ws-hidden summary").click();
    await outline.locator("details.ws-hidden").getByLabel("Confirm").check();
    expect((await outline.locator(".ws-row.cause .ck-tag").allInnerTexts()).sort()).toEqual(["Ask the author", "Caller not updated",
      "Confirm", "Confirm", "Result handled the old way", "Unchanged reader"]);
    await expect(page.getByRole("region", { name: "Coverage" })).toContainText("Risks judged by rules only.");
    await expect(page.getByRole("region", { name: "Build impact" })).toContainText("include/hal/regs.h declaration change → 4 files rebuild");
    await expect(page.getByRole("region", { name: "Coverage" })).toContainText("No test code found in the workspace");
    await expectNoNodeIds(page);
    await expectNamed(page);
    await threads.first().getByRole("link", { name: "Go to thread A's first unread story" }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
  });

  test("the overview gives each thread its intro and a way into its first unread story", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const card = page.locator(".ov-thread").first();
    await expect(card.locator(".ov-purpose")).toHaveCount(2);                            // its purpose, then the fixed intro
    await expect(card.locator(".ov-purpose").last()).toContainText("Starts with “hal_write's signature changed");
    await expect(card.locator(".ov-purpose .ai-label")).toHaveCount(0);
    await card.getByRole("link", { name: "Go to thread A's first unread story" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2$`));
    await expectNamed(page);
  });

  test("Looks fine marks a check's place for everyone and survives a re-run", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    const row = outline.getByRole("link", { name: /^Open check: uart_init calls hal_write/ });
    await row.click();
    const panel = page.getByRole("complementary", { name: /^Check: uart_init calls hal_write/ });
    await panel.getByRole("button", { name: "Looks fine & next" }).click();
    await expect(panel.locator(".ck-mark")).toHaveText("Looks fine · demo · just now");
    await expect(row.locator(".ws-cdone")).toHaveText("✓");
    await expect(page.locator(".ws-progress")).toHaveText("0 of 5 stories read · 3 causes open");
    await rerun(page, base);
    await page.reload();                                                             // the cause keeps its id across the re-run
    await expect(row.locator(".ws-cdone")).toHaveText("✓");
    await panel.getByRole("button", { name: "Reopen" }).click();
    await expect(row.locator(".ws-cdone")).toHaveText("0/1");
  });

  test("a check's place takes a comment thread of its own", async ({ page }) => {
    await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await outline.getByRole("link", { name: /^Open check: logger_flush ignores the result/ }).click();
    const panel = page.getByRole("complementary", { name: /^Check: logger_flush ignores the result/ });
    await panel.getByRole("button", { name: "Comment" }).click();
    await panel.getByPlaceholder("Leave a comment…").fill("flush should retry");
    await panel.locator(".comments").getByRole("button", { name: "Comment" }).click();
    await expect(panel.locator(".comments")).toContainText("flush should retry");
    await expect(panel.getByRole("button", { name: "Comment (1)" })).toBeVisible();
  });

  test("a story: its thread, what it does, its tabs, its call paths and the checks on its flows", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S2`);
    const head = page.locator(".ws-story-head");
    await expect(head.locator(".st-crumb")).toHaveText(/^Thread A · story 1 of 2 · feeds: /);
    await expect(head.locator(".ws-story-meta .ws-chip").first()).toHaveText("CL 102 · 1 function");
    const chips = page.getByRole("region", { name: /^Flow 1: / }).locator(".st-chip");      // the checks on its flow, Confirm hidden
    await expect(chips).toHaveText(["uart_init calls hal_write and was not updated for its new signature"]);
    await expect(chips.first()).toHaveClass(/\bcaller\b/);
    await chips.first().click();
    const check = page.getByRole("complementary", { name: "Check: uart_init calls hal_write and was not updated for its new signature" });
    await expect(check.locator(".cs-pos")).toHaveText("1 / 1");
    await check.getByRole("link", { name: "Close the check" }).click();
    await expect(page.locator(".ws-detail")).toHaveCount(0);
    const tabs = page.getByRole("navigation", { name: "Story sections" });
    await tabs.getByRole("link", { name: /^Before → after/ }).click();
    const contract = page.getByRole("region", { name: "Before → after" });
    await expect(contract).toContainText("hal_write: gained unsigned");
    await expect(contract.locator("mark")).toHaveText("unsigned");
    await tabs.getByRole("link", { name: /^Call paths/ }).click();
    const paths = page.getByRole("region", { name: /^Call paths/ });
    await expect(paths.locator(".st-steps")).toHaveText(["contractmain→uart_init→hal_write",
      "callmain→logger_flush→uart_send→hal_write", "callmain→logger_write→uart_send→hal_write"]);
    await tabs.getByRole("link", { name: /^Where/ }).click();
    await page.getByRole("region", { name: "Where" }).getByRole("link", { name: "Open hal_write in hal/regs.c at line 10" }).click();
    await expect(page.getByRole("complementary", { name: "Code: regs.c" })).toBeVisible();
    await head.getByRole("link", { name: /^Next story: S1/ }).click();
    await expect(head.locator(".st-crumb")).toHaveText(/^Thread A · story 2 of 2 · after: /);
    await expect(page.locator(".st-place")).toHaveText("Uses what story 1 adds.");
    await expect(page.getByRole("region", { name: /^Flow 1: / }).locator(".st-chip")).toHaveText([
      "logger_flush ignores the result of uart_send, which can now return -2", "uart_errors reads Uart::errors, which uart_send now writes"]);
    await tabs.getByRole("link", { name: /^Call paths/ }).click();
    await expect(paths.locator(".st-steps").nth(1)).toHaveText("statemain→… 2 more→Uart::errors→uart_errors");
    await paths.getByRole("button", { name: "Show the 2 folded steps" }).click();
    await expect(paths.locator(".st-steps").nth(1)).toHaveText("statemain→logger_write→uart_send→Uart::errors→uart_errors");
    await expectNoNodeIds(page);
    await expectNamed(page);
    await paths.getByRole("link", { name: /On the graph/ }).first().click();
    await expect(page).toHaveURL(/\/s\/S1\?view=graph&flow=1/);
    await expect(page.locator(".bd-node").first()).toBeVisible();
  });

  test("the outline: the overview, each thread with its stories in reading order, its checks and the Index", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await expect(outline.getByRole("link", { name: "Go to the overview" })).toContainText("Medium risk · rules only");
    await expect(outline.locator(".ws-thread h3")).toHaveText(["A hal_write in hal, 3 open, 0 of 2 read", "B logger_init in service, 0 of 2 read",
                                                               "C svc::Engine::step in cpp, 1 open, 0 of 1 read"]);
    await expect(outline.locator(".ws-thread").first().getByRole("link", { name: /^Go to story/ })).toHaveCount(2);
    await expect(outline.locator(".ws-thread").first().getByRole("link", { name: /^Go to story/ }).nth(1)).toHaveAccessibleName(/^Go to story S1/);
    await outline.getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Thread A");
    await openIndex(page, "Files");
    await expect(page).toHaveURL(new RegExp(`${base}/i/files$`));
    await expect(page.getByRole("tab", { name: /^Files/ })).toHaveAttribute("aria-selected", "true");
    await page.getByRole("link", { name: "Open logger.c's diff" }).click();
    await expect(page.getByRole("complementary", { name: "Code: logger.c" })).toBeVisible();
    await page.getByRole("tab", { name: /^CLs/ }).click();
    await page.getByRole("link", { name: "Open CL 104" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/cl/104$`));
    await outline.getByRole("button", { name: "Checks" }).click();
    await expect(outline.locator(".ws-row.cause")).toHaveCount(4);
    await expectNamed(page);
  });

  test("old addresses: a finding opens the stepper on its story, its Details the finding, #map the Index's map", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const findings = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/findings`)).json() as { id: string; title: string; severity: string }[];
    const sig = findings.find((f) => f.title === "hal_write: signature changed")!;
    await page.goto(`${base}/f/${sig.id}`);
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?open=cause%3Ac[0-9a-f]{10}&at=1$`));
    const panel = page.getByRole("complementary", { name: "Check: hal_write: signature changed" });
    await panel.getByRole("link", { name: `Finding ${sig.id}'s details` }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?open=finding%3A${sig.id}$`));
    await expect(page.locator(".ws-detail .ws-finding h2")).toContainText("hal_write: signature changed");
    const info = findings.find((f) => f.severity === "info")!;
    await page.goto(`${base}/f/${info.id}`);
    await expect(page.locator(".ws-finding h2")).toBeVisible();
    await page.goto(`${base}#map`);
    await expect(page).toHaveURL(new RegExp(`${base}/i/map$`));
    await expect(page.getByRole("region", { name: "The map" })).toBeVisible();
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the overview's connections are sentences and nothing scrolls sideways", async ({ page }) => {
    await startReview(page, FOUR);
    await page.getByRole("link", { name: "Go to the overview" }).click();
    await expect(page.locator(".ov-conn-rows li")).toHaveText(["A and B: both run inside main",
                                                               "B and C: nothing besides arriving in CL 104 — ask the author"]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });

  test("a story's tabs wrap on a phone", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    await expect(page.getByRole("navigation", { name: "Story sections" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
