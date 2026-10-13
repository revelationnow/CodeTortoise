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
