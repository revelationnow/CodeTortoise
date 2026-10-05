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

/** As startStories, then open the same review in the workspace (spec 2026-10-04-review-workspace; `/w/` while built). */
export async function startWorkspace(page: Page): Promise<string> {
  await startStories(page);
  const id = page.url().match(/\/r\/(\d+)/)![1];
  await page.goto(`/w/${id}`);
  await expect(page.locator(".ws-rail")).toBeVisible({ timeout: 60_000 });
  return `/w/${id}`;
}

/** No node id is ever shown (spec §8): visible text never matches N<digits>. */
export async function expectNoNodeIds(page: Page) {
  const text = await page.locator("main").innerText();
  expect(text.match(/\bN\d+\b/g) ?? []).toEqual([]);
}

/** Every link and button on the page has an accessible name (spec §8). */
export async function expectNamed(page: Page) {
  const unnamed = await page.locator("main a, main button, main [role=button]").evaluateAll((els) =>
    els.filter((e) => !(e.getAttribute("aria-label") || e.textContent?.trim() || e.getAttribute("title")))
       .map((e) => e.outerHTML.slice(0, 120)));
  expect(unnamed).toEqual([]);
}

/** The flow strip's ‹ › keep their place across flows and its row never scrolls sideways (spec §3.6, §8). */
export async function flowStripHolds(page: Page) {
  const strip = page.getByRole("region", { name: "Flow" });
  const next = strip.getByRole("button", { name: "Next flow" });
  const at = (await next.boundingBox())!.x;
  const row = strip.locator(".ws-flow-row");
  for (let i = 0; i < 3; i++) {
    expect(await row.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    await next.click();
    expect((await next.boundingBox())!.x).toBe(at);
  }
}
