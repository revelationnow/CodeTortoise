import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

const SINKS = "http://127.0.0.1:8794";
const READER = "uart_errors reads Uart::errors";

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
    await cov.getByRole("button", { name: "Show" }).click();
    await expect(cov).toContainText(/shared sinks? shown: .*Stats::tx/);
    await page.goto(`${base}/f/${sunk.id}?details=1`);
    await expect(title).toBeVisible();
    await page.goto(base);
    await cov.getByRole("button", { name: "Hide" }).click();
    await expect(cov).toContainText(/shared sinks? hidden/);
  });

  test("the owner marks a field from To check; a re-run hides its rows and unmarking brings them back", async ({ page }) => {
    await startReview(page);
    const row = page.locator(".ck-row", { hasText: READER });
    await row.getByRole("button", { name: "Treat Uart::errors as a sink" }).click();
    await expect(row).toContainText("Marked — re-run to apply");
    await row.getByRole("button", { name: "Re-run" }).click();
    const cov = page.getByRole("region", { name: "Coverage" });
    await expect(cov).toContainText("Uart::errors (marked)", { timeout: 60_000 });
    await expect(page.locator(".ck-row", { hasText: READER })).toHaveCount(0);
    await cov.getByRole("button", { name: "Unmark Uart::errors" }).click();
    await expect(cov).toContainText("Unmarked — re-run to apply");
    await cov.getByRole("button", { name: "Re-run" }).click();
    await expect(page.locator(".ck-row", { hasText: READER })).toHaveCount(1, { timeout: 60_000 });
    await expect(cov).not.toContainText("Uart::errors");
  });
});
