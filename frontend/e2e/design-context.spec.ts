import { devices, expect } from "@playwright/test";
import { login, reviewMenu, sideways, startReview, STRONG, test } from "./helpers";

// e2e/serve-strong.sh's fake strong model (e2e/fake_llm.py) says in its verdict when the prompt carries a design context.
const NOTES = "The UART must never drop a byte: a write that is too long is refused whole, and its sender is told.";

async function openPanel(page: import("@playwright/test").Page) {
  await (await reviewMenu(page)).getByRole("menuitem", { name: "Design context…" }).click();
  const panel = page.getByRole("dialog", { name: "Design context" });
  await expect(panel).toBeVisible();
  return panel;
}

test.describe("the design context", () => {
  test.use({ baseURL: STRONG, viewport: { width: 1440, height: 900 } });

  test("the owner gives the review a design context; the design stage runs again and the opening says it read it", async ({ page }) => {
    await startReview(page);
    const verdict = page.locator(".ov-top .dz-verdict");
    await expect(verdict.locator(".dz-src")).toHaveText("AI, from the stories");
    const panel = await openPanel(page);
    await panel.getByLabel("Notes").fill(NOTES);
    await expect(panel.locator(".dc-count")).toHaveText(`${NOTES.length} of 12,000 characters`);
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(panel.getByRole("status")).toContainText("Saved");
    await expect(verdict.locator(".dz-src")).toHaveText("AI, from the stories and the design context", { timeout: 30_000 });
    await expect(verdict.locator("p.ai-text")).toContainText("against its design context");
    await expect(page.getByRole("region", { name: "What it must get right" }).locator(".dz-src"))
      .toHaveText("AI, from the stories and the design context");
  });

  test("a condition added by hand leads the condition fold, and one the code lacks is said in the panel", async ({ page }) => {
    await startReview(page);
    const panel = await openPanel(page);
    await panel.getByLabel("Condition, as the code writes it").fill("reg == REG_CTRL");
    await panel.getByLabel("In the function (optional)").fill("hal_write");
    await panel.getByRole("button", { name: "Add the condition" }).click();
    await panel.getByLabel("Condition, as the code writes it").fill("x == 1");
    await panel.getByRole("button", { name: "Add the condition" }).click();
    await expect(panel.locator(".dc-added li")).toHaveCount(2);
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("heading", { name: /Writes to any other register · \d+ changes? still runs?$/ }))
      .toBeVisible({ timeout: 30_000 });   // its name starts "Written by AI: ", the AI mark
    await expect(panel.locator(".dc-notes li")).toHaveText(["The condition x == 1 is not in the changed functions."]);
  });

  test("someone else in the review reads the design context but has nothing to change it with", async ({ page, browser }) => {
    const base = await startReview(page);
    const panel = await openPanel(page);
    await panel.getByLabel("Notes").fill(NOTES);
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(panel.getByRole("status")).toContainText("Saved");
    const context = await browser.newContext({ baseURL: STRONG });
    const other = await context.newPage();
    await login(other, "bob");
    await other.goto(base);
    const theirs = await openPanel(other);
    await expect(theirs.locator(".dc-read")).toContainText(NOTES);
    await expect(theirs.getByRole("textbox")).toHaveCount(0);
    await expect(theirs.getByRole("button", { name: "Save" })).toHaveCount(0);
    await context.close();
  });

  test("the owner's unsaved draft comes back when the panel closes, until it is saved or discarded (final review I5)", async ({ page }) => {
    await startReview(page);
    let panel = await openPanel(page);
    await expect(panel.getByText("Unsaved changes")).toHaveCount(0);
    await panel.getByLabel("Notes").fill(NOTES);
    await panel.getByLabel("Condition, as the code writes it").fill("len > 64");
    await expect(panel.getByText("Unsaved changes")).toBeVisible();
    await panel.getByLabel("Notes").press("Escape");                                   // Escape, even in a text field, closes it
    await expect(panel).toBeHidden();
    panel = await openPanel(page);
    await expect(panel.getByLabel("Notes")).toHaveValue(NOTES);
    await expect(panel.getByLabel("Condition, as the code writes it")).toHaveValue("len > 64");
    await page.getByRole("region", { name: "Centre" }).click({ position: { x: 5, y: 5 } });   // and so does a press outside
    await expect(panel).toBeHidden();
    panel = await openPanel(page);
    await expect(panel.getByLabel("Notes")).toHaveValue(NOTES);
    await panel.getByRole("button", { name: "Discard" }).click();
    await expect(panel.getByLabel("Notes")).toHaveValue("");
    await expect(panel.getByLabel("Condition, as the code writes it")).toHaveValue("");
    await expect(panel.getByText("Unsaved changes")).toHaveCount(0);
    await panel.getByLabel("Notes").fill(NOTES);
    await panel.getByRole("button", { name: "Save" }).click();
    await expect(panel.getByRole("status")).toContainText("Saved");
    await expect(panel.getByText("Unsaved changes")).toHaveCount(0);
    await page.keyboard.press("Escape");
    panel = await openPanel(page);
    await expect(panel.getByLabel("Notes")).toHaveValue(NOTES);                        // as saved, not as a draft
    await expect(panel.getByText("Unsaved changes")).toHaveCount(0);
  });

  test("a review started with a design context opens with the opening that read it", async ({ page }) => {
    await login(page);
    await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
    await page.getByLabel("Design context (optional)").fill(NOTES);
    await page.getByRole("button", { name: "Start review" }).click();
    await expect(page.locator(".ov-top .dz-verdict .dz-src")).toHaveText("AI, from the stories and the design context",
                                                                          { timeout: 60_000 });
  });
});

test.describe("the design context's limits (final review I4)", () => {
  test.use({ baseURL: STRONG, viewport: { width: 1440, height: 900 } });

  test("the creation form counts the design context and holds back a start over the cap", async ({ page }) => {
    await login(page);
    await page.getByLabel("Changelists (shelved or submitted)").fill("101");
    const field = page.getByLabel("Design context (optional)"), start = page.getByRole("button", { name: "Start review" });
    await field.fill(`  ${"x".repeat(12_001)}  `);
    await expect(page.locator(".rv-ctx-count")).toHaveText("12,001 of 12,000 characters");
    await expect(page.locator(".rv-ctx-count")).toHaveClass(/over/);
    await expect(start).toBeDisabled();
    await field.fill("x".repeat(12_000));
    await expect(page.locator(".rv-ctx-count")).toHaveText("12,000 of 12,000 characters");
    await expect(start).toBeEnabled();
  });

  test("a link's document is named by its page, and the lists stop at what the context holds", async ({ page }) => {
    await startReview(page);
    await page.route("**/api/reviews/*/design-context", async (r) => {      // a server that lists a site to read links from
      if (r.request().method() !== "GET") return r.fallback();
      const res = await r.fetch();
      await r.fulfill({ response: res, json: { ...(await res.json()), links: true } });
    });
    const panel = await openPanel(page);
    await panel.getByLabel("Link").fill(`https://wiki.example.com/display/${"HW/".repeat(80)}UART%20Driver%20Design`);
    await panel.getByRole("button", { name: "Add the link" }).click();
    await expect(panel.locator(".dc-docs li")).toHaveText(["UART Driver Design (read when saved) Remove"]);
    for (let i = 1; i < 10; i++) {
      await panel.getByLabel("Add a file").setInputFiles({ name: `note-${i}.md`, mimeType: "text/markdown", buffer: Buffer.from("x") });
      await expect(panel.locator(".dc-docs li")).toHaveCount(i + 1);
    }
    await expect(panel.getByLabel("Add a file")).toBeDisabled();
    await panel.getByLabel("Link").fill("https://wiki.example.com/design/more");
    await expect(panel.getByRole("button", { name: "Add the link" })).toBeDisabled();
    await expect(panel.getByText("The context holds at most 10 documents; remove one to add another.")).toBeVisible();
    for (let i = 0; i < 10; i++) {
      await panel.getByLabel("Condition, as the code writes it").fill(`x == ${i}`);
      await panel.getByRole("button", { name: "Add the condition" }).click();
    }
    await panel.getByLabel("Condition, as the code writes it").fill("x == 10");
    await expect(panel.getByRole("button", { name: "Add the condition" })).toBeDisabled();
    await expect(panel.getByText("The context holds at most 10 added conditions.")).toBeVisible();
    await panel.getByRole("button", { name: "Save" }).click();       // this server reads no links: refused in a sentence
    await expect(panel.getByRole("alert")).toHaveText(/^UART Driver Design: This server reads no links/);
  });
});

test.describe("the design context on a phone", () => {
  test.use({ baseURL: STRONG, viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
             deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the panel fits the phone's width and nothing scrolls sideways", async ({ page }) => {
    await startReview(page);
    const panel = await openPanel(page);
    await panel.getByLabel("Notes").fill(NOTES);
    const box = await panel.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(devices["iPhone 13"].viewport.width);
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });
});
