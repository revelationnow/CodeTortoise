import { expect, type Page, test } from "@playwright/test";
import { hold, login, openFold, openIndex, SINKS, startReview } from "./helpers";

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
      await expect(row.getByRole("alert"), "a screen reader is told of the refusal").toHaveText("a run is already in progress");
      await expect(row.getByRole("button", { name: "Re-run" })).toBeEnabled();
    } finally {
      await page.request.delete(`/api/sinks/${encodeURIComponent("Uart::errors")}`);
    }
  });

  test("a mark the server refuses says so; pressed again, the old failure is gone while it waits, and a success leaves none beside it", async ({ page }) => {
    const row = await openReader(page);
    try {
      // a refusal with no words in it: what the page has to go on when the status line is empty too, as over HTTP/2
      await page.route("**/api/sinks/*", (r) => r.fulfill({ status: 500, json: { detail: "" } }));
      const treat = row.getByRole("button", { name: "Treat Uart::errors as a sink" });
      await treat.click();
      await expect(row.getByRole("alert")).toHaveText("The field could not be marked as a sink.");
      const waiting = await hold(page, "**/api/sinks/*");                    // the server takes it this time, but not yet
      await treat.click();
      await waiting.held;
      await expect(row.getByRole("alert"), "a new attempt clears the last failure at once").toHaveCount(0);
      waiting.release();
      await expect(row).toContainText("Marked — re-run to apply");
      await expect(row.getByRole("alert"), "a success leaves no old failure beside it").toHaveCount(0);
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

  test("a list of shared sinks that will not load again after an unmark keeps its card and says so; the next load clears it", async ({ page }) => {
    await login(page);
    const labels = ["Probe::one", "Probe::two"];
    for (const l of labels) await page.request.put(`/api/sinks/${encodeURIComponent(l)}`);
    try {
      await page.goto("/health");
      const card = page.locator("section.card", { has: page.getByRole("heading", { name: "Shared sinks" }) });
      await expect(card).toContainText("Probe::one");
      const list = { refusing: true };
      // a refusal with no words in it: what the page has to go on when the status line is empty too, as over HTTP/2
      await page.route("**/api/sinks", (route) => list.refusing ? route.fulfill({ status: 500, json: { detail: "" } }) : route.continue());
      await card.getByRole("button", { name: "Unmark Probe::one" }).click();
      await expect(card.getByRole("alert")).toHaveText("The shared sinks could not be loaded.");
      await expect(card.getByRole("heading", { name: "Shared sinks" }), "the card stays").toBeVisible();
      const second = card.getByRole("button", { name: "Unmark Probe::two" });
      await expect(second, "what the card showed before stays").toBeVisible();
      list.refusing = false;
      await second.click();
      await expect(card).not.toContainText("Probe::");                          // the list loaded again: neither is on it
      await expect(card.getByRole("alert"), "a later load clears the failure").toHaveCount(0);
    } finally {
      for (const l of labels) await page.request.delete(`/api/sinks/${encodeURIComponent(l)}`);
    }
  });
});
