import { devices, expect, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startReview } from "./helpers";

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
    const left = page.locator(".ov2-left");
    await expect(left.locator("h2")).toHaveText(["The change as a whole", "How the threads connect", "Threads", /^The map/, "Discussion"]);
    await expect(left.locator(".ws-lead")).toHaveText("3 threads: A and B: both run inside main; B and C: nothing besides arriving in CL 104.");
    const conn = page.locator(".ov-conn");
    await expect(conn.locator(".ov-box")).toHaveCount(3);
    await expect(conn.locator(".ov-arc")).toHaveCount(2);
    await expect(conn.locator(".ov-arc.dashed")).toHaveCount(1);                        // only bundled: dashed, ask the author
    await expect(conn.locator(".ov-arc-label")).toHaveText(["both run inside main", "nothing besides arriving in CL 104 — ask the author"]);
    await conn.locator(".ov-arc-label").first().hover();                                 // pointing at an arc lights both threads
    await expect(conn.locator(".ov-box.hot")).toHaveCount(2);
    await expect(conn.locator(".ov-box").nth(2)).not.toHaveClass(/\bhot\b/);
    const threads = left.locator(".ov-thread");
    await expect(threads.locator("h3")).toHaveText(["hal_write in hal", "logger_init in service", "svc::Engine::step in cpp"]);
    await expect(threads.first().locator(".ov-reason")).toHaveText(["← calls 1"]);
    const check = page.getByRole("region", { name: "To check" });
    await expect(check.locator("h3 .ck-count")).toHaveText("6 open");
    await expect(check.locator(".ck-group h4")).toHaveText(["A · hal_write in hal", "C · svc::Engine::step in cpp"]);
    await expect(check.locator(".ck-row > .ck-top .ck-tag")).toHaveText(["Confirm", "Confirm", "Caller not updated",
                                                                         "Result handled the old way", "Unchanged reader", "Ask the author"]);
    await expect(check).toContainText("Risks judged by rules only.");
    await expect(page.getByRole("region", { name: "Build impact" })).toContainText("include/hal/regs.h declaration change → 4 files rebuild");
    await expect(page.getByRole("region", { name: "Coverage" })).toContainText("No test code found in the workspace");
    await expectNoNodeIds(page);
    await expectNamed(page);
    await threads.first().getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page).toHaveURL(/\/s\/S1$/);
  });

  test("Looks fine marks a check for everyone, greys it below the open ones and survives a re-run", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const check = page.getByRole("region", { name: "To check" });
    const row = check.locator(".ck-row", { hasText: "uart_init calls hal_write" });
    await row.getByRole("button", { name: "Looks fine" }).click();
    await expect(row).toHaveClass(/\bmarked\b/);
    await expect(row.locator(".ck-mark")).toHaveText("Looks fine · demo · just now");
    await expect(check.locator("h3 .ck-count")).toHaveText("5 open");
    await expect(check.locator(".ck-group").first().locator(".ck-row").last()).toHaveClass(/\bmarked\b/);   // below the open rows
    await rerun(page, base);
    await page.reload();
    await expect(check.locator(".ck-row", { hasText: "uart_init calls hal_write" })).toHaveClass(/\bmarked\b/);
    await expect(check.locator("h3 .ck-count")).toHaveText("5 open");
    await check.locator(".ck-row", { hasText: "uart_init calls hal_write" }).getByRole("button", { name: "Reopen" }).click();
    await expect(check.locator("h3 .ck-count")).toHaveText("6 open");
  });

  test("a check takes a comment thread of its own", async ({ page }) => {
    await startReview(page, FOUR);
    const row = page.getByRole("region", { name: "To check" }).locator(".ck-row", { hasText: "logger_flush ignores the result" });
    await row.getByRole("button", { name: "Comment" }).click();
    await row.getByPlaceholder("Leave a comment…").fill("flush should retry");
    await row.locator(".comments").getByRole("button", { name: "Comment" }).click();
    await expect(row.locator(".comments")).toContainText("flush should retry");
    await expect(row.getByRole("button", { name: "Comment (1)" })).toBeVisible();
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("To check comes first, folded to its count, and the connections are sentences", async ({ page }) => {
    await startReview(page, FOUR);
    await page.getByRole("link", { name: "Go to the whole change" }).click();
    const check = page.locator("details.ck-tile");
    await expect(check).not.toHaveAttribute("open");
    await expect(check.locator("summary .ck-count")).toHaveText("6 open");
    const tile = (await check.boundingBox())!, whole = (await page.getByRole("heading", { name: "The change as a whole" }).boundingBox())!;
    expect(tile.y).toBeLessThan(whole.y);
    await expect(page.locator(".ov-conn-rows li")).toHaveText(["A and B: both run inside main",
                                                               "B and C: nothing besides arriving in CL 104 — ask the author"]);
    await check.locator("summary").click();
    await expect(check.locator(".ck-row")).toHaveCount(6);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
