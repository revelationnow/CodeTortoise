import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

test("owner reviews fixture CLs end to end", async ({ page }) => {
  await startReview(page);
  await expect(page.getByRole("tablist", { name: "Call flows" }).getByRole("tab")).toHaveCount(3);

  await page.getByRole("link", { name: /Findings/ }).click();
  await expect(page.getByText("uart_send now writes Uart::errors through a local alias")).toBeVisible();

  // line comments are made in the board's file viewer (the one place files are shown)
  await page.getByRole("link", { name: "Board" }).click();
  await page.locator(".bd-about .tree .file", { hasText: "uart.c" }).first().click();
  const viewer = page.locator(".bd-viewer");
  await viewer.getByRole("button", { name: "Stacked" }).click();
  await viewer.locator(".bd-ln.a", { hasText: "return -2;" }).first().click();
  await viewer.getByPlaceholder("Leave a comment…").fill("Does logger_flush handle -2?");
  await viewer.getByRole("button", { name: "Comment", exact: true }).click();
  await expect(viewer.getByText("Does logger_flush handle -2?")).toBeVisible();

  // the same line comment shows on the board, in the changed function's card (cards are pills while files are open)
  await viewer.getByRole("button", { name: "Close all" }).click();
  await expect(page.locator(".bd-card", { hasText: "uart_send" }).getByText("Does logger_flush handle -2?")).toBeVisible();
});
