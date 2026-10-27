import { devices, expect, type Locator, type Page, test } from "@playwright/test";
import { barNames, expectNamed, expectNoNodeIds, openIndex, sideways, startReview } from "./helpers";

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
    await expect(page.locator(".ov3 h2")).toHaveText(["3 threads", "Build impact · up to 4 files rebuild", "Coverage · 2 notes",
                                                      "Discussion · no comments yet"]);
    await expect(page.locator(".ov3 .ws-lead"))                                         // the heading counts the threads
      .toHaveText("A and B: both run inside main; B and C: nothing besides arriving in CL 104.");
    await expect(page.locator(".ov-links li")).toHaveText(["With Thread A: both run inside main",
                                                           "With Thread B: nothing besides arriving in CL 104 — ask the author"]);
    const threads = page.locator("section.ov-sec");
    await expect(threads.locator(".ov-sec-name")).toHaveText(["hal_write in hal", "logger_init in service", "svc::Engine::step in cpp"]);
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
    await threads.first().getByRole("link", { name: "Start thread A" }).click();
    await expect(page).toHaveURL(/\/s\/S2$/);
  });

  test("the overview gives each thread its intro and a way into its first unread story", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const card = page.locator("section.ov-sec").first();
    await expect(card.locator(".ov-purpose")).toHaveCount(2);                            // its purpose, then the fixed intro
    await expect(card.locator(".ov-purpose").last()).toContainText("Starts with “hal_write's signature changed");
    await expect(card.locator(".ov-purpose").last())                                     // the kinds, with no count and no Confirm
      .toContainText("Checks open: Caller not updated, Result handled the old way, Unchanged reader.");
    await expect(card.locator(".ov-purpose.ai-text")).toHaveCount(0);
    await card.getByRole("link", { name: "Start thread A" }).click();
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
    await expect(page.locator(".ws-progress")).toHaveText("0 of 5 stories read · 3 checks open");
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

  /** A check's comment box on the default server's "logger_flush ignores the result" check; returns the panel. */
  async function openCheckTalk(page: Page) {
    await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await outline.getByRole("button", { name: "Checks" }).click();
    await outline.getByRole("link", { name: /^Open check: logger_flush ignores the result/ }).click();
    const panel = page.getByRole("complementary", { name: /^Check: logger_flush ignores the result/ });
    await panel.getByRole("button", { name: "Comment" }).click();
    return panel;
  }
  /** The server refuses every write to a comment while `refusing.on` (a comment or reply posted, a thread resolved, a comment edited
   * or deleted), with no words in it: what the page has to go on when the status line is empty too, as over HTTP/2. */
  async function refuseWrites(page: Page) {
    const refusing = { on: true };
    await page.route((u) => /\/api\/(comments\/\d+|reviews\/\d+\/comments)$/.test(u.pathname), (route) =>
      refusing.on && route.request().method() !== "GET" ? route.fulfill({ status: 500, json: { detail: "" } }) : route.continue());
    return refusing;
  }

  test("a comment the server refuses to post says so beside the box and keeps the draft; sent again it posts and the alert goes", async ({ page }) => {
    const panel = await openCheckTalk(page);
    const composer = panel.locator(".comments > .composer");               // the box for a new thread, whatever its placeholder says
    const box = composer.getByRole("textbox"), send = composer.getByRole("button", { name: "Comment" });
    const refusing = await refuseWrites(page);
    await box.fill("flush should retry");
    await send.click();
    await expect(panel.getByRole("alert")).toHaveText("The comment could not be posted.");
    await expect(box, "the draft stays in its box").toHaveValue("flush should retry");
    await expect(send, "…ready to be sent again").toBeEnabled();
    await expect(panel.locator(".thread")).toHaveCount(0);
    refusing.on = false;
    await send.click();
    await expect(panel.locator(".thread")).toContainText("flush should retry");
    await expect(panel.getByRole("alert"), "a later success clears it").toHaveCount(0);
    await expect(box).toHaveValue("");
  });

  test("a reply, Resolve, Reopen, edit and delete the server refuses each say so beside their thread, and the draft stays", async ({ page }) => {
    const panel = await openCheckTalk(page);
    await panel.getByPlaceholder("Leave a comment…").fill("flush should retry");
    await panel.locator(".comments").getByRole("button", { name: "Comment" }).click();
    const thread = panel.locator(".thread"), comment = thread.locator(".comment");
    await expect(thread).toContainText("flush should retry");
    const refusing = await refuseWrites(page);
    const aboutThread = thread.locator(":scope > [role=alert]"), aboutComment = comment.getByRole("alert");

    const reply = thread.getByPlaceholder("Reply…");                       // a reply
    await reply.fill("and log it");
    await thread.getByRole("button", { name: "Reply", exact: true }).click();
    await expect(aboutThread).toHaveText("The reply could not be posted.");
    await expect(reply, "the reply stays in its box").toHaveValue("and log it");
    await thread.getByRole("button", { name: "Resolve", exact: true }).click();    // Resolve: the thread's own line says this now
    await expect(aboutThread).toHaveText("The thread could not be resolved.");
    await expect(thread).not.toHaveClass(/\bresolved\b/);
    refusing.on = false;
    await thread.getByRole("button", { name: "Resolve", exact: true }).click();
    await expect(thread).toHaveClass(/\bresolved\b/);
    await expect(aboutThread, "a later success clears it").toHaveCount(0);
    refusing.on = true;
    await thread.getByRole("button", { name: "Reopen", exact: true }).click();
    await expect(aboutThread).toHaveText("The thread could not be reopened.");
    await expect(thread).toHaveClass(/\bresolved\b/);
    refusing.on = false;
    await thread.getByRole("button", { name: "Reopen", exact: true }).click();
    await expect(thread).not.toHaveClass(/\bresolved\b/);
    await expect(aboutThread).toHaveCount(0);

    refusing.on = true;                                                    // an edit
    await comment.getByRole("button", { name: "edit", exact: true }).click();
    const edit = comment.getByRole("textbox");
    await edit.fill("flush should retry twice");
    await comment.getByRole("button", { name: "Save", exact: true }).click();
    await expect(aboutComment).toHaveText("The edit could not be saved.");
    await expect(edit, "the edit stays in its box").toHaveValue("flush should retry twice");
    await comment.getByRole("button", { name: "Cancel", exact: true }).click();     // Cancel gives the edit up, and its failure with it
    await expect(edit).toHaveCount(0);
    await expect(aboutComment, "a failure under a comment no longer being edited would be stale").toHaveCount(0);
    await comment.getByRole("button", { name: "edit", exact: true }).click();       // started again and refused again, it says so again
    await edit.fill("flush should retry twice");
    await comment.getByRole("button", { name: "Save", exact: true }).click();
    await expect(aboutComment).toHaveText("The edit could not be saved.");
    refusing.on = false;
    await comment.getByRole("button", { name: "Save", exact: true }).click();
    await expect(comment).toContainText("flush should retry twice");
    await expect(aboutComment).toHaveCount(0);

    refusing.on = true;                                                    // a delete
    await comment.getByRole("button", { name: "delete", exact: true }).click();
    await expect(aboutComment).toHaveText("The comment could not be deleted.");
    await expect(comment).toContainText("flush should retry twice");
    refusing.on = false;
    await comment.getByRole("button", { name: "delete", exact: true }).click();
    await expect(thread).toHaveCount(0);
  });

  test("a resolved thread fades its own words but not its failures: a refused Reopen and a refused delete read at full strength", async ({ page }) => {
    const panel = await openCheckTalk(page);
    await panel.getByPlaceholder("Leave a comment…").fill("flush should retry");
    await panel.locator(".comments").getByRole("button", { name: "Comment" }).click();
    const thread = panel.locator(".thread"), comment = thread.locator(".comment");
    await thread.getByRole("button", { name: "Resolve", exact: true }).click();
    await expect(thread).toHaveClass(/\bresolved\b/);
    /** How much of its colour an element shows: the product of its own opacity and its ancestors'. */
    const shown = (el: Locator) => el.evaluate((node) => {
      let o = 1;
      for (let e: Element | null = node; e; e = e.parentElement) o *= Number(getComputedStyle(e).opacity);
      return o;
    });
    const words = comment.locator(".comment-body"), reopen = thread.getByRole("button", { name: "Reopen", exact: true });
    expect(await shown(words), "a resolved thread fades its words").toBe(0.6);
    expect(await shown(reopen), "…and its buttons").toBe(0.6);
    await refuseWrites(page);
    await reopen.click();
    const aboutThread = thread.locator(":scope > [role=alert]"), aboutComment = comment.getByRole("alert");
    await expect(aboutThread).toHaveText("The thread could not be reopened.");
    expect(await shown(aboutThread), "a refused Reopen reads at full strength").toBe(1);
    await comment.getByRole("button", { name: "delete", exact: true }).click();
    await expect(aboutComment).toHaveText("The comment could not be deleted.");
    expect(await shown(aboutComment), "so does a refused delete").toBe(1);
    expect(await shown(words), "the words stay faded beside them").toBe(0.6);
    expect(await shown(reopen), "…and the buttons").toBe(0.6);
  });

  test("a story: its thread, what it does, its tabs, its call paths and the checks on its flows", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S2`);
    const head = page.locator(".ws-story-head");
    await expect(head.locator(".st-crumb")).toHaveText(/^Thread A · story 1 of 2 · feeds: /);
    await expect(head.locator(".ws-story-meta .ws-chip").first()).toHaveText("CL 102 · 1 function");
    const chips = page.getByRole("region", { name: "hal_write's signature changed" }).locator(".st-chip");   // its group's checks, Confirm hidden
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
    await expect(page.getByRole("region", { name: "uart_send returns new values" }).locator(".st-chip"))
      .toHaveText(["logger_flush ignores the result of uart_send, which can now return -2"]);
    await expect(page.getByRole("region", { name: "Uart::errors gets a new writer: uart_send" }).locator(".st-chip"))
      .toHaveText(["uart_errors reads Uart::errors, which uart_send now writes"]);
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
    await expect(outline.getByRole("link", { name: "Go to the overview" })).toHaveText("⌂ Overview");   // the header has the risk
    await expect.poll(() => barNames(page)).toEqual(["Thread A: hal_write in hal, 3 open, 0 of 2 read",
      "Thread B: logger_init in service, 0 of 2 read", "Thread C: svc::Engine::step in cpp, 1 open, 0 of 1 read"]);
    await outline.getByRole("button", { name: /^Thread A:/ }).click();
    const rows = outline.locator(".ws-bar-list > li > .ws-row.story");
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(1)).toHaveAccessibleName(/^Go to story S1/);
    await rows.nth(1).click();
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
    await expect(page.locator(".ov-links li")).toHaveText(["With Thread A: both run inside main",
                                                           "With Thread B: nothing besides arriving in CL 104 — ask the author"]);
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });

  test("a story's tabs wrap on a phone", async ({ page }) => {
    const base = await startReview(page, FOUR);
    await page.goto(`${base}/s/S1`);
    await expect(page.getByRole("navigation", { name: "Story sections" })).toBeVisible();
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });
});
