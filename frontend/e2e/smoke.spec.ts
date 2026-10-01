import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

test("owner reviews fixture CLs end to end", async ({ page }) => {
  await startReview(page);
  await expect(page.getByRole("tab")).toHaveCount(3);

  await page.getByRole("link", { name: /Findings/ }).click();
  await expect(page.getByText("uart_send now writes Uart::errors through a local alias")).toBeVisible();

  await page.getByRole("link", { name: /Files/ }).click();
  const row = page.locator("tr.add", { hasText: "return -2;" });
  await row.hover();
  await row.getByTitle("Comment on this line").click();
  await page.getByPlaceholder("Leave a comment…").fill("Does logger_flush handle -2?");
  await page.getByRole("button", { name: "Comment" }).click();
  await expect(page.getByText("Does logger_flush handle -2?")).toBeVisible();

  // the same line comment shows on the board, in the changed function's card
  await page.getByRole("link", { name: "Board" }).click();
  await expect(page.locator(".bd-card", { hasText: "uart_send" }).getByText("Does logger_flush handle -2?")).toBeVisible();
});
