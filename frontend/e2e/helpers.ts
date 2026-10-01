import { expect, type Page } from "@playwright/test";

/** Log in as the demo owner, review fixture CLs 101+102 and wait for the board. */
export async function startReview(page: Page) {
  await page.goto("/login");
  await page.getByLabel("P4 user").fill("demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();
  await page.goto("/new");
  await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.locator(".bd-node").first()).toBeVisible({ timeout: 60_000 });
}
