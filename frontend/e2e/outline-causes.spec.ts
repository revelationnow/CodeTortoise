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
