import { expect, type Page } from "@playwright/test";

export async function login(page: Page, user = "demo") {
  await page.goto("/login");
  await page.getByLabel("P4 user").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();
}

/** Log in as the demo owner, review fixture CLs 101+102 from the landing page and wait for the story list. */
export async function startStories(page: Page) {
  await login(page);
  await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.locator(".st-entry").first()).toBeVisible({ timeout: 60_000 });
}

/** As startStories, then open the board ("Boards ›" on the story list). */
export async function startReview(page: Page) {
  await startStories(page);
  await page.getByRole("link", { name: "Boards ›" }).click();
  // desktop shows the canvas; phones open on the flow reader (spec §13)
  await expect(page.locator(".bd-node, .ph-step").first()).toBeVisible({ timeout: 60_000 });
}
