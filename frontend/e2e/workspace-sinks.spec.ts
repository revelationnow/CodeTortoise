import { expect, type Page, test } from "@playwright/test";
import { login, openFold, openIndex, startReview } from "./helpers";

const SINKS = "http://127.0.0.1:8794";
const READER = "uart_errors reads Uart::errors";

/** Open the reader's check from the outline's Checks; returns the stepper's sink mark. */
async function openReader(page: Page) {
  await startReview(page);
  const outline = page.locator("aside.ws-outline");
  await outline.getByRole("button", { name: "Checks" }).click();
  await outline.getByRole("link", { name: new RegExp(`^Open check: ${READER}`) }).click();
  return page.getByRole("complementary", { name: new RegExp(`^Check: ${READER}`) }).locator(".cs-acts .sink-mark");
}

/** Shared sinks (spec 2026-10-09-shared-sinks): this server's tortoise.yaml lists Stats::*. */
test.describe("shared sinks", () => {
  test.use({ baseURL: SINKS });

  test("a write to a listed sink is hidden until the viewer shows it", async ({ page }) => {
    const base = await startReview(page);
    const cov = page.getByRole("region", { name: "Coverage" });
    await expect(cov).toContainText(/shared sinks? hidden: .*Stats::tx \(in tortoise\.yaml\)/);
    const rid = base.split("/").pop();
    const all: { id: string; title: string; sink?: boolean }[] = await (await page.request.get(`/api/reviews/${rid}/findings`)).json();
    const sunk = all.find((f) => f.sink && f.title.startsWith("uart_send now writes Stats::tx"))!;
    expect(sunk).toBeTruthy();
    const title = page.getByRole("heading", { name: /uart_send now writes Stats::tx/ });
    await page.goto(`${base}/f/${sunk.id}?details=1`);
    await expect(page.getByText(`Finding ${sunk.id} isn't in this review.`)).toBeVisible();
    await expect(title).toHaveCount(0);
    await page.goto(base);
    await openFold(page, "Coverage");
    await cov.getByRole("button", { name: "Show" }).click();
    await expect(cov).toContainText(/shared sinks? shown: .*Stats::tx/);
    await page.goto(`${base}/f/${sunk.id}?details=1`);
    await expect(title).toBeVisible();
    await page.goto(base);
    await openFold(page, "Coverage");
    await cov.getByRole("button", { name: "Hide" }).click();
    await expect(cov).toContainText(/shared sinks? hidden/);
  });

  test("the owner marks a field from its reader's check; a re-run hides the check and unmarking brings it back", async ({ page }) => {
    const mark = await openReader(page);
    await mark.getByRole("button", { name: "Treat Uart::errors as a sink" }).click();
    await expect(mark).toContainText("Marked — re-run to apply");
    await mark.getByRole("button", { name: "Re-run" }).click();
    const cov = page.getByRole("region", { name: "Coverage" });
    await expect(cov).toContainText("Uart::errors (marked)", { timeout: 60_000 });
    const rows = page.locator("aside.ws-outline .ws-row.cause", { hasText: READER });
    await expect(rows).toHaveCount(0);
    await openFold(page, "Coverage");
    await cov.getByRole("button", { name: "Unmark Uart::errors" }).click();
    await expect(cov).toContainText("Unmarked — re-run to apply");
    await cov.getByRole("button", { name: "Re-run" }).click();
    await expect(rows).toHaveCount(1, { timeout: 60_000 });
    await expect(cov).not.toContainText("Uart::errors");
  });

  test("Show reveals the writer's quiet note in its code; hidden, the code has none", async ({ page }) => {
    const base = await startReview(page);
    const openDiff = async () => {
      await openIndex(page, "Files");
      await page.getByRole("link", { name: "Open uart.c's diff" }).click();
      const file = page.getByRole("complementary", { name: "Code: uart.c" });
      await expect(file.locator(".bd-ann", { hasText: "Uart::errors" }).first()).toBeVisible();
      return file.locator(".bd-ann", { hasText: "a shared sink (in tortoise.yaml)" });
    };
    await expect(await openDiff()).toHaveCount(0);
    await page.goto(base);
    await (await openFold(page, "Coverage")).getByRole("button", { name: "Show" }).click();
    await expect((await openDiff()).first()).toContainText("writes Stats::tx");
  });

  test("a re-run that fails says why, and the button can be tried again", async ({ page }) => {
    const row = await openReader(page);
    try {
      await row.getByRole("button", { name: "Treat Uart::errors as a sink" }).click();
      await page.route("**/rerun", (r) => r.fulfill({ status: 409, contentType: "application/json",
                                                      body: JSON.stringify({ detail: "a run is already in progress" }) }));
      await row.getByRole("button", { name: "Re-run" }).click();
      await expect(row).toContainText("a run is already in progress");
      await expect(row.getByRole("button", { name: "Re-run" })).toBeEnabled();
    } finally {
      await page.request.delete(`/api/sinks/${encodeURIComponent("Uart::errors")}`);
    }
  });

  test("unmarking on the Health page takes the label off the list", async ({ page }) => {
    await login(page);
    await page.request.put(`/api/sinks/${encodeURIComponent("Probe::flag")}`);
    await page.goto("/health");
    const card = page.locator("section.card", { has: page.getByRole("heading", { name: "Shared sinks" }) });
    await expect(card).toContainText("Probe::flag");
    await card.getByRole("button", { name: "Unmark Probe::flag" }).click();
    await expect(card).not.toContainText("Probe::flag");
  });
});
