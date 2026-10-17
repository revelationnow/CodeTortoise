import { devices, expect, type Page, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startReview } from "./helpers";

/** The outline and checks by cause (spec 2026-10-16-outline-and-causes): fixture CLs 101–104 make three threads; with
 * Confirm hidden their causes are a caller, a result and a reader in thread A and an ask in thread C. */
const FOUR = "101 102 103 104";

/** The reading as a review stored before causes: no `causes`, no `cause` on its checks. */
async function withoutCauses(page: Page) {
  const strip = async (route: import("@playwright/test").Route) => {
    const res = await route.fetch();
    const j = await res.json();
    const r = j.reading ?? j;
    if (r && typeof r === "object") { delete r.causes; for (const k of r.checks ?? []) delete k.cause; }
    await route.fulfill({ response: res, json: j });
  };
  await page.route("**/api/reviews/*/reading", strip);
  await page.route("**/api/reviews/*/stories/*", strip);
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the outline's Stories: threads with open causes, the current story's flows", async ({ page }) => {
    const base = await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await expect(outline.getByRole("button", { name: "Stories" })).toHaveAttribute("aria-pressed", "true");
    await expect(outline.locator(".ws-thread h3")).toHaveText(["A hal_write in hal, 3 open, 0 of 2 read",
      "B logger_init in service, 0 of 2 read", "C svc::Engine::step in cpp, 1 open, 0 of 1 read"]);
    await outline.getByRole("link", { name: /^Go to story S1/ }).click();
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
    await startReview(page, FOUR);
    const outline = page.locator("aside.ws-outline");
    await expect(outline.locator(".ws-thread h3").first()).toHaveText("A hal_write in hal, 0 of 2 read");
    await outline.getByRole("button", { name: "Checks" }).click();
    await expect(outline).toContainText("Re-run the review to group its checks.");
  });
});
