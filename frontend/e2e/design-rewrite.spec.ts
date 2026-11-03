import { devices, expect, type Locator, type Page } from "@playwright/test";
import { login, reviewMenu, sideways, startReview, STRONG, test } from "./helpers";

// e2e/serve-strong.sh's fake strong model (e2e/fake_llm.py) writes the verdict again, shorter when the instruction asks,
// and a walk-through's title as "A long write, told again".
const SHORT = "One new result goes unchecked. Settle whether logger_flush must handle the new -2.";

// the source line of words a reader steered says so (final review I2); e2e's reader signs in as "demo"
const STEERED = "rewritten as demo asked: “Make it shorter”";

const verdictRow = (page: Page) => page.locator(".ov-top .dz-verdict");

/** Opens the Rewrite ▾ menu inside `at` (the verdict's row by default) and returns it. */
async function rewriteMenu(page: Page, at: Locator = verdictRow(page)) {
  await at.getByRole("button", { name: "Rewrite", exact: true }).click();
  const menu = at.getByRole("menu", { name: "Rewrite" });
  await expect(menu).toBeVisible();
  return menu;
}

async function shorter(page: Page) {
  const v = verdictRow(page);
  await (await rewriteMenu(page)).getByRole("menuitem", { name: "Rewrite with an instruction…" }).click();
  const box = v.getByLabel("How should the AI rewrite it?");
  await expect(box).toBeFocused();
  await box.fill("Make it shorter");
  await v.getByRole("button", { name: "Ask" }).click();
  await expect(v.locator("p.ai-text")).toHaveText(`Written by AI. ${SHORT}`, { timeout: 30_000 });
  await expect(box).toHaveCount(0);
  await expect(v.locator(".dz-src")).toHaveText(`AI, from the stories · ${STEERED}`);
}

test.describe("the design overview's AI menu", () => {
  test.use({ baseURL: STRONG, viewport: { width: 1440, height: 900 } });

  test("anyone in the review rewrites the verdict, after a confirmation, and the new words show", async ({ page }) => {
    await startReview(page);
    const v = verdictRow(page);
    await expect(v.locator("p.ai-text")).toContainText("The change holds together, but one new result goes unchecked.");
    page.once("dialog", (d) => d.accept());
    await (await rewriteMenu(page)).getByRole("menuitem", { name: "Rewrite", exact: true }).click();
    await expect(v.locator("p.ai-text")).toContainText("The change holds together once more", { timeout: 30_000 });
    await expect(v.locator(".dz-src")).toHaveText("AI, from the stories · rewritten at demo's request");
  });

  test("a rewrite with an instruction puts the reader's words to the model", async ({ page }) => {
    await startReview(page);
    await shorter(page);
  });

  test("the owner pins the verdict; a design re-run keeps it, and a pinned part is not rewritten", async ({ page }) => {
    await startReview(page);
    const v = verdictRow(page);
    await shorter(page);
    await (await rewriteMenu(page)).getByRole("menuitem", { name: "Pin this text" }).click();
    await expect(v.locator(".dz-src")).toHaveText(`AI, from the stories · pinned · ${STEERED}`);
    // a design context runs the design stage again; its fresh verdict would say it read the context
    await (await reviewMenu(page)).getByRole("menuitem", { name: "Design context…" }).click();
    const panel = page.getByRole("dialog", { name: "Design context" });
    await panel.getByLabel("Notes").fill("The UART must never drop a byte.");
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(v.locator(".dz-src")).toHaveText(`AI, from the stories and the design context · pinned · ${STEERED}`,
                                                  { timeout: 30_000 });
    await expect(v.locator("p.ai-text")).toHaveText(`Written by AI. ${SHORT}`);
    await page.keyboard.press("Escape");
    const menu = await rewriteMenu(page);
    await expect(menu.getByRole("menuitem", { name: "Rewrite", exact: true })).toBeDisabled();
    await expect(menu.getByRole("menuitem", { name: "Unpin" })).toBeVisible();
  });

  test("someone else in the review may rewrite but has no pin", async ({ page, browser }) => {
    const base = await startReview(page);
    const context = await browser.newContext({ baseURL: STRONG, viewport: { width: 1440, height: 900 } });
    const other = await context.newPage();
    await login(other, "bob");
    await other.goto(base);
    await expect((await rewriteMenu(other)).getByRole("menuitem")).toHaveText(["Rewrite", "Rewrite with an instruction…"]);
    await context.close();
  });

  test("a walk-through's title and lead are rewritten on its page", async ({ page }) => {
    await startReview(page);
    await page.locator(".dz-walks a").first().click();
    const head = page.locator(".dz-walk .st-head");
    await expect(head.locator(".dz-src")).toHaveText("AI, from the stories");
    page.once("dialog", (d) => d.accept());
    await (await rewriteMenu(page, head)).getByRole("menuitem", { name: "Rewrite", exact: true }).click();
    await expect(head.getByRole("heading", { level: 2 })).toContainText("A long write, told again", { timeout: 30_000 });
    await expect(head.locator(".dz-src")).toHaveText("AI, from the stories · rewritten at demo's request");
  });
});

test.describe("the AI menu says why and keeps focus (phase 4 M6, M7, M8)", () => {
  test.use({ baseURL: STRONG, viewport: { width: 1440, height: 900 } });

  test("after Pin or Unpin, focus is back on the Rewrite button", async ({ page }) => {
    await startReview(page);
    const v = verdictRow(page), button = v.getByRole("button", { name: "Rewrite", exact: true });
    await (await rewriteMenu(page)).getByRole("menuitem", { name: "Pin this text" }).click();
    await expect(v.locator(".dz-src")).toHaveText("AI, from the stories · pinned");
    await expect(button).toBeFocused();
    await (await rewriteMenu(page)).getByRole("menuitem", { name: "Unpin" }).click();
    await expect(v.locator(".dz-src")).toHaveText("AI, from the stories");
    await expect(button).toBeFocused();
  });

  test("a pinned part says why it can't be rewritten: in the owner's menu, and beside a shut Rewrite for anyone else",
       async ({ page, browser }) => {
    const base = await startReview(page);
    await (await rewriteMenu(page)).getByRole("menuitem", { name: "Pin this text" }).click();
    await expect(verdictRow(page).locator(".dz-src")).toHaveText("AI, from the stories · pinned");
    await expect((await rewriteMenu(page)).getByText("Pinned: unpin it to rewrite it")).toBeVisible();
    const context = await browser.newContext({ baseURL: STRONG, viewport: { width: 1440, height: 900 } });
    const other = await context.newPage();
    await login(other, "bob");
    await other.goto(base);
    const theirs = verdictRow(other);
    await expect(theirs.getByRole("button", { name: "Rewrite", exact: true })).toBeDisabled();
    await expect(theirs.getByText("Pinned by the review's owner")).toBeVisible();
    await context.close();
  });

  test("a refused rewrite says so and offers the owner Raise budget; a failed one shows its error", async ({ page }) => {
    await startReview(page);
    const v = verdictRow(page);
    await page.route("**/api/reviews/*/design/verdict/rewrite", (r) =>
      r.fulfill({ status: 429, json: { detail: "you've used your 20 AI calls today" } }));
    page.once("dialog", (d) => d.accept());
    await (await rewriteMenu(page)).getByRole("menuitem", { name: "Rewrite", exact: true }).click();
    await expect(v.getByRole("alert")).toContainText("you've used your 20 AI calls today");
    await expect(v.getByRole("alert").getByRole("button", { name: "Raise budget" })).toBeVisible();
    await page.unroute("**/api/reviews/*/design/verdict/rewrite");
    await (await rewriteMenu(page)).getByRole("menuitem", { name: "Rewrite with an instruction…" }).click();
    await v.getByLabel("How should the AI rewrite it?").fill("Make it fail the checks");
    await v.getByRole("button", { name: "Ask" }).click();
    await expect(v.getByRole("alert")).toHaveText(/^the AI's answer didn't pass the checks \(citations or house style\); nothing was changed/,
                                                  { timeout: 30_000 });
    await expect(v.getByRole("alert").getByRole("button", { name: "Raise budget" })).toHaveCount(0);
  });
});

test.describe("the AI menu on a phone", () => {
  test.use({ baseURL: STRONG, viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
             deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the open menu stays on the phone's screen and nothing scrolls sideways", async ({ page }) => {
    await startReview(page);
    await page.getByRole("link", { name: "Go to the overview" }).click();       // a phone opens on the outline
    const box = await (await rewriteMenu(page)).boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(devices["iPhone 13"].viewport.width);
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });
});
