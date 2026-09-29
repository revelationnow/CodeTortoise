import { expect, test } from "@playwright/test";

test("owner reviews fixture CLs end to end", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("P4 user").fill("demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();

  await page.getByRole("link", { name: "New review" }).click();
  await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("heading", { name: "Summary" })).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("heading", { name: "L2: driver" })).toBeVisible();

  await page.getByRole("link", { name: "Call flows" }).click();
  await expect(page.getByTestId("flow-graph").locator("canvas").first()).toBeAttached();

  await page.getByRole("link", { name: /Findings/ }).click();
  await expect(page.getByText("uart_send now writes Uart::errors through a local alias")).toBeVisible();

  await page.getByRole("link", { name: /Files/ }).click();
  const row = page.locator("tr.add", { hasText: "return -2;" });
  await row.hover();
  await row.getByTitle("Comment on this line").click();
  await page.getByPlaceholder("Leave a comment…").fill("Does logger_flush handle -2?");
  await page.getByRole("button", { name: "Comment" }).click();
  await expect(page.getByText("Does logger_flush handle -2?")).toBeVisible();
});
