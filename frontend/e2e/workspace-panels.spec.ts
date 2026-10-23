import { expect, type Page, test } from "@playwright/test";
import { hold, openIndex, startReview } from "./helpers";

/** The side panel, folding and the Index's new views (spec 2026-10-12-story-account-and-panels §2-§5). */

const FOUR = "101 102 103 104";
type F = { id: string; title: string; severity: string; state: string };
const findingsOf = async (page: Page, base: string) =>
  await (await page.request.get(`/api/reviews/${base.split("/")[2]}/findings`)).json() as F[];

test.use({ viewport: { width: 1400, height: 900 } });

test("a check's Details opens its finding in the side panel; the story stays and Back returns to the check", async ({ page }) => {
  const base = await startReview(page, FOUR);
  const sig = (await findingsOf(page, base)).find((f) => f.title === "hal_write: signature changed")!;
  await page.goto(`${base}/f/${sig.id}`);                                     // the stepper on its story
  const check = page.getByRole("complementary", { name: "Check: hal_write: signature changed" });
  await check.getByRole("link", { name: `Finding ${sig.id}'s details` }).click();
  await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?open=finding%3A${sig.id}$`));
  const panel = page.getByRole("complementary", { name: `Finding: ${sig.id}` });
  await expect(panel.locator("h2")).toContainText("hal_write: signature changed");
  await expect(panel.getByRole("link", { name: "Open as a page" })).toHaveAttribute("href", `${base}/f/${sig.id}?details=1`);
  await expect(page.getByRole("navigation", { name: "Story sections" })).toBeVisible();   // the story stays
  await page.goBack();
  await expect(check).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?open=cause%3Ac[0-9a-f]{10}&at=1$`));
});

test("a finding the review lacks shows Not found in the panel", async ({ page }) => {
  const base = await startReview(page);
  await page.goto(`${base}/s/S1?open=finding:F999`);
  await expect(page.getByRole("complementary", { name: "Finding: F999" })).toContainText("Finding F999 isn't in this review.");
});
test("the panel keeps a tab per item opened; a tab switches back and × closes it", async ({ page }) => {
  const base = await startReview(page, FOUR);
  const sig = (await findingsOf(page, base)).find((f) => f.title === "hal_write: signature changed")!;
  await page.goto(`${base}/f/${sig.id}`);
  const check = page.getByRole("complementary", { name: "Check: hal_write: signature changed" });
  await check.getByRole("link", { name: `Finding ${sig.id}'s details` }).click();
  const tabs = page.getByRole("list", { name: "Open items" });
  await expect(tabs.getByRole("link", { name: /^Show / })).toHaveCount(2);
  await expect(tabs.getByRole("link", { name: "Show hal_write: signature changed" })).toBeVisible();   // the cause beside the finding
  await expect(tabs.locator("a[aria-current='true']")).toHaveText(sig.id);
  await tabs.getByRole("link", { name: "Show hal_write: signature changed" }).click();
  await expect(check).toBeVisible();
  await tabs.getByRole("link", { name: `Show ${sig.id}` }).click();
  await expect(page.getByRole("complementary", { name: `Finding: ${sig.id}` })).toBeVisible();
  const entries = await page.evaluate(() => history.length);
  await tabs.getByRole("button", { name: `Close ${sig.id}` }).click();     // the active one: its neighbour shows
  await expect(check).toBeVisible();
  await expect(page.getByRole("list", { name: "Open items" })).toHaveCount(0);   // one tab left: no bar
  expect(await page.evaluate(() => history.length)).toBe(entries);          // closing is not a step to go Back over
});

test("the outline folds to a strip and stays folded; Focus folds it and widens the panel until pressed again", async ({ page }) => {
  const base = await startReview(page);
  await page.goto(`${base}/s/S1`);
  const index = page.locator("aside.ws-outline details.ws-index");
  await index.locator("summary").click();
  await expect(index).toHaveAttribute("open", "");
  await page.getByRole("button", { name: "Fold the contents" }).click();
  await expect(page.locator(".ws-rail.folded")).toContainText("Contents");
  await page.getByRole("button", { name: "Unfold the contents" }).click();
  await expect(index).toHaveAttribute("open", "");                          // folding hides the outline, it keeps its state
  await page.getByRole("button", { name: "Fold the contents" }).click();
  await page.reload();
  await expect(page.locator(".ws-rail.folded")).toBeVisible();
  await page.getByRole("button", { name: "Unfold the contents" }).click();
  await expect(page.locator(".ws-rail.folded")).toHaveCount(0);

  await openIndex(page, "Files");
  await page.getByRole("link", { name: "Open uart.c's diff" }).click();
  const panel = page.locator(".ws-detail");
  const before = (await panel.boundingBox())!.width;
  await panel.getByRole("button", { name: "Focus" }).click();
  await expect(page.locator(".ws-rail.folded")).toBeVisible();
  expect((await panel.boundingBox())!.width).toBeGreaterThan(before);
  expect((await page.getByRole("region", { name: "Centre" }).boundingBox())!.width).toBeGreaterThanOrEqual(359);
  const focusedW = (await panel.boundingBox())!.width;
  await page.setViewportSize({ width: 1700, height: 900 });                  // a wider window: the panel takes the room
  await expect.poll(async () => (await panel.boundingBox())!.width).toBeGreaterThan(focusedW + 250);
  await page.setViewportSize({ width: 1400, height: 900 });
  await expect.poll(async () => (await panel.boundingBox())!.width).toBeLessThan(focusedW + 2);
  await panel.getByRole("button", { name: "Focus" }).click();                // pressed again: as it was
  await expect(page.locator(".ws-rail.folded")).toHaveCount(0);
  expect(Math.abs((await panel.boundingBox())!.width - before)).toBeLessThan(2);
  await panel.getByRole("button", { name: "Focus" }).click();
  await page.goBack();                                                       // the panel closes: the outline comes back
  await expect(page.locator(".ws-detail")).toHaveCount(0);
  await expect(page.locator(".ws-rail.folded")).toHaveCount(0);
});

test("with storage blocked the outline still folds for the visit", async ({ page }) => {
  const base = await startReview(page);
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => { throw new Error("blocked"); };
    Storage.prototype.setItem = () => { throw new Error("blocked"); };
  });
  await page.goto(`${base}/s/S1`);
  await expect(page.locator(".ws-rail.folded")).toHaveCount(0);
  await page.getByRole("button", { name: "Fold the contents" }).click();
  await expect(page.locator(".ws-rail.folded")).toBeVisible();
});

test("Index › Findings lists every finding worst first, filters by severity and status, and opens one in the panel", async ({ page }) => {
  const base = await startReview(page);
  const all = await findingsOf(page, base);
  await openIndex(page, "Findings");
  await expect(page).toHaveURL(new RegExp(`${base}/i/findings$`));
  await expect(page.getByRole("tab", { name: `Findings (${all.length})` })).toHaveAttribute("aria-selected", "true");
  const list = page.getByRole("region", { name: "Findings" });
  const rows = list.locator(".ix-findings-list > li");
  await expect(rows).toHaveCount(all.length);
  const rank = ["high", "medium", "low", "info"];
  const sevs = (await rows.locator(".badge").allTextContents()).map((s) => rank.indexOf(s.trim()));
  expect(sevs).toEqual([...sevs].sort((a, b) => a - b));
  const top = rank[sevs[0]];
  await list.getByLabel("Severity").selectOption(top);
  await expect(page).toHaveURL(new RegExp(`/i/findings\\?sev=${top}$`));
  await expect(rows).toHaveCount(all.filter((f) => f.severity === top).length);
  await list.getByLabel("Status").selectOption("dismissed");
  await expect(page).toHaveURL(new RegExp(`sev=${top}&status=dismissed$`));
  await expect(list).toContainText("No findings match.");
  await list.getByLabel("Status").selectOption("");
  await rows.first().getByRole("link", { name: /^Open finding F\d+ in the side panel$/ }).click();
  await expect(page).toHaveURL(new RegExp(`/i/findings\\?open=finding%3AF\\d+&sev=${top}$`));
  await expect(page.getByRole("complementary", { name: /^Finding: F\d+$/ }).locator("h2")).toBeVisible();
  await expect(rows.first()).toBeVisible();                                   // the list stays
  const bg = (el: Element) => getComputedStyle(el).backgroundColor;
  expect(await rows.first().evaluate(bg)).not.toBe("rgba(0, 0, 0, 0)");    // the opened row is marked
});

test("Index › CLs expands a CL's files in place and opens a file's diff in the panel without leaving", async ({ page }) => {
  const base = await startReview(page);
  await page.goto(`${base}/i/cls`);
  await page.getByRole("button", { name: "Show CL 101's files" }).click();
  const file = page.getByRole("link", { name: /^Open .+'s diff in CL 101$/ }).first();
  await file.click();
  await expect(page).toHaveURL(new RegExp(`${base}/i/cls\\?open=file.*&cl=101$`));
  const panel = page.getByRole("complementary", { name: /^Code: / });
  await expect(panel).toBeVisible();
  await expect(panel.getByLabel("Changelist")).toHaveValue("101");                       // that CL's diff, not all CLs
  await expect(page.getByRole("button", { name: "Hide CL 101's files" })).toBeVisible();      // the list stays as it was
  await page.getByRole("button", { name: "Expand all" }).click();
  await expect(page.getByRole("button", { name: "Hide CL 102's files" })).toBeVisible();
  await page.getByRole("button", { name: "Collapse all" }).click();
  await expect(page.getByRole("link", { name: /'s diff in CL \d+$/ })).toHaveCount(0);
});

test("a review opened again with a CL's diff in the panel asks for that file's change once and shows that CL's diff", async ({ page }) => {
  const base = await startReview(page);
  await page.goto(`${base}/i/cls`);
  await page.getByRole("button", { name: "Show CL 101's files" }).click();
  await page.getByRole("link", { name: /^Open .+'s diff in CL 101$/ }).first().click();
  const panel = page.getByRole("complementary", { name: /^Code: / });
  await expect(panel.getByLabel("Changelist")).toHaveValue("101");
  const asked: string[] = [];
  page.on("request", (r) => { const m = new URL(r.url()).pathname.match(/^\/api\/reviews\/\d+\/(file|source)$/); if (m) asked.push(m[1]); });
  const files = await hold(page, "**/api/reviews/*/files");
  await page.reload();
  await files.held;
  await expect(panel).toBeVisible();                      // the panel opens before the list of changed files is in
  await page.waitForTimeout(500);
  await expect(panel).not.toContainText("unchanged");
  files.release();
  await expect(panel.getByLabel("Changelist")).toHaveValue("101");
  expect(asked).toEqual(["file"]);
});
