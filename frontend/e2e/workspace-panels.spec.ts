import { expect, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

/** The side panel, folding and the Index's new views (spec 2026-10-12-story-account-and-panels §2-§5). */

const FOUR = "101 102 103 104";
type F = { id: string; title: string; severity: string; state: string };
const findingsOf = async (page: Page, base: string) =>
  await (await page.request.get(`/api/reviews/${base.split("/")[2]}/findings`)).json() as F[];

test.use({ viewport: { width: 1400, height: 900 } });

test("a check's Details opens its finding in the side panel; the story stays and Back closes it", async ({ page }) => {
  const base = await startReview(page, FOUR);
  const sig = (await findingsOf(page, base)).find((f) => f.title === "hal_write: signature changed")!;
  await page.goto(`${base}/s/S2`);
  const row = page.getByRole("region", { name: "To check" }).locator(`.ck-row[data-finding="${sig.id}"]`);
  await row.getByRole("link", { name: `Finding ${sig.id}'s details` }).click();
  await expect(page).toHaveURL(new RegExp(`${base}/s/S2\\?open=finding%3A${sig.id}$`));
  const panel = page.getByRole("complementary", { name: `Finding: ${sig.id}` });
  await expect(panel.locator("h2")).toContainText("hal_write: signature changed");
  await expect(panel.getByRole("link", { name: "Open as a page" })).toHaveAttribute("href", `${base}/f/${sig.id}?details=1`);
  await expect(page.getByRole("region", { name: "To check" })).toBeVisible();          // the story stays
  await page.goBack();
  await expect(page.locator(".ws-detail")).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`${base}/s/S2$`));
});

test("a finding the review lacks shows Not found in the panel", async ({ page }) => {
  const base = await startReview(page);
  await page.goto(`${base}/s/S1?open=finding:F999`);
  await expect(page.getByRole("complementary", { name: "Finding: F999" })).toContainText("Finding F999 isn't in this review.");
});
test("the panel keeps a tab per item opened; a tab switches back and × closes it", async ({ page }) => {
  const base = await startReview(page, FOUR);
  const sig = (await findingsOf(page, base)).find((f) => f.title === "hal_write: signature changed")!;
  await page.goto(`${base}/s/S2`);
  const row = page.getByRole("region", { name: "To check" }).locator(`.ck-row[data-finding="${sig.id}"]`);
  await row.getByRole("link", { name: `Finding ${sig.id}'s details` }).click();
  await row.getByRole("link", { name: /^Open / }).click();                 // the row's file, at its line
  const tabs = page.getByRole("tablist", { name: "Open items" });
  await expect(tabs.getByRole("tab")).toHaveCount(2);
  await expect(tabs.getByRole("tab", { selected: true })).toHaveText(/\.[ch]$/);
  await tabs.getByRole("tab", { name: sig.id }).click();
  await expect(page.getByRole("complementary", { name: `Finding: ${sig.id}` })).toBeVisible();
  await tabs.getByRole("button", { name: `Close ${sig.id}` }).click();     // the active one, first: its right neighbour shows
  await expect(page.getByRole("complementary", { name: /^Code: / })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Open items" })).toHaveCount(0);   // one tab left: no bar
});

test("the rail and To check fold to strips and stay folded; Focus folds both and widens the panel until pressed again", async ({ page }) => {
  const base = await startReview(page);
  await page.goto(`${base}/s/S1`);
  await page.getByRole("button", { name: "Fold the contents" }).click();
  await expect(page.locator(".ws-rail.folded")).toContainText("Contents");
  await page.getByRole("button", { name: "Fold To check" }).click();
  await expect(page.locator(".ws-strip.right .ws-strip-name")).toHaveText(/^To check · \d+ open$/);
  await page.reload();
  await expect(page.locator(".ws-rail.folded")).toBeVisible();
  await expect(page.locator(".ws-strip.right")).toBeVisible();
  await page.getByRole("button", { name: "Unfold the contents" }).click();
  await page.getByRole("button", { name: "Unfold To check" }).click();
  await expect(page.locator(".ws-rail.folded")).toHaveCount(0);
  await expect(page.locator(".ws-strip.right")).toHaveCount(0);

  await page.getByRole("region", { name: "To check" }).getByRole("link", { name: /^Open / }).first().click();
  const panel = page.locator(".ws-detail");
  const before = (await panel.boundingBox())!.width;
  await panel.getByRole("button", { name: "Focus" }).click();
  await expect(page.locator(".ws-rail.folded")).toBeVisible();
  await expect(page.locator(".ws-strip.right")).toBeVisible();
  expect((await panel.boundingBox())!.width).toBeGreaterThan(before);
  expect((await page.getByRole("region", { name: "Centre" }).boundingBox())!.width).toBeGreaterThanOrEqual(359);
  await panel.getByRole("button", { name: "Focus" }).click();                // pressed again: as it was
  await expect(page.locator(".ws-rail.folded")).toHaveCount(0);
  expect(Math.abs((await panel.boundingBox())!.width - before)).toBeLessThan(2);
  await panel.getByRole("button", { name: "Focus" }).click();
  await page.goBack();                                                       // the panel closes: the columns come back
  await expect(page.locator(".ws-detail")).toHaveCount(0);
  await expect(page.locator(".ws-rail.folded")).toHaveCount(0);
  await expect(page.locator(".ws-strip.right")).toHaveCount(0);
});

test("with storage blocked the columns still fold for the visit", async ({ page }) => {
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
