import { devices, expect } from "@playwright/test";
import { expectNamed, expectNoNodeIds, openFold, sideways, startReview, STRONG, test } from "./helpers";

// e2e/serve-strong.sh: CLs 101 and 102, stories from the fake strong model (e2e/fake_llm.py), whose design answer
// writes the verdict, three concerns, three ownership lines, the walk-throughs' titles and the condition's false case.
const VERDICT = "The change holds together, but one new result goes unchecked. Settle whether logger_flush must handle the new -2.";
const HAZARD = "logger_flush ignores the new -2, so a failed send goes unnoticed.";

test.describe("the strong model's design text", () => {
  test.use({ baseURL: STRONG, viewport: { width: 1440, height: 900 } });

  test("the verdict says what to settle and names its check as a chip, edged as AI", async ({ page }) => {
    await startReview(page);
    const verdict = page.locator(".ov-top .dz-verdict");
    await expect(verdict.locator("p.ai-text")).toHaveText(`Written by AI. ${VERDICT}`);
    await expect(verdict.locator(".st-chip")).toHaveText([HAZARD]);
    await expect(verdict.locator(".dz-src")).toHaveText("AI, from the stories");
    await verdict.locator(".st-chip").click();
    await expect(page.locator(".cs")).toBeVisible();                        // a chip opens its check, as chips do elsewhere
  });

  test("what it must get right is a row per concern: how the change does it, where, and its assessment", async ({ page }) => {
    await startReview(page);
    const section = page.getByRole("region", { name: "What it must get right" }), rows = section.locator("tbody tr");
    await expect(section.locator(".dz-src")).toHaveText("AI, from the stories");
    await expect(section.locator(".dz-table")).toHaveClass(/\bai-text\b/);
    await expect(section.locator("thead th")).toHaveText(["Concern", "How the change does it", "Where", "Assessment"]);
    await expect(rows).toHaveCount(3);
    const first = rows.first();
    await expect(first.locator("td").nth(0)).toHaveText("1 Senders learn when a write is too long");   // numbered, as story crumbs cite them
    await expect(first.locator("td").nth(1)).toHaveText("uart_send now returns -2 for a write longer than 64 bytes.");
    await expect(first.locator(".dz-c-where .ov-letter")).toHaveText(["A"]);
    await expect(first.locator(".dz-c-where a")).toHaveText(["S1"]);
    await expect(first.locator(".dz-c-note")).toHaveText(" logger_flush drops the -2.");
    await expect(first.locator(".st-chip")).toHaveText([HAZARD]);
    await expect(rows.locator(".ck-tag")).toHaveText(["confirm", "right", "note"]);
    await expect(rows.nth(2).locator(".dz-c-where a")).toHaveText(["S1", "S2"]);
    await expectNamed(page);
    await expectNoNodeIds(page);
    await first.locator(".dz-c-where a").click();
    await expect(page).toHaveURL(/\/s\/S1(\?|$)/);
  });

  test("is the design right? counts its questionable lines and shortfalls, each line tagged and citing its code or story", async ({ page }) => {
    await startReview(page);
    await expect(page.getByRole("heading", { name: "Is the design right? · 1 questionable · 1 shortfall" })).toBeVisible();
    const fold = await openFold(page, "Is the design right?"), lines = fold.locator("ul.dz-owner > li");
    await expect(lines).toHaveCount(3);
    await expect(lines.locator(".ck-tag")).toHaveText(["right", "questionable", "shortfall"]);
    await expect(lines.nth(1).locator(".ck-tag")).toHaveClass(/\bconfirm\b/);       // a questionable line looks like a confirm tag
    await expect(lines.first()).toHaveClass(/\bai-text\b/);
    await expect(lines.first()).toContainText("The driver owns the length check.");
    await expect(lines.first().locator(".dz-cites code")).toHaveText(["driver/uart.c"]);
    await expect(lines.nth(1).locator(".dz-cites a")).toHaveText(["S1"]);
    await expectNoNodeIds(page);
  });

  test("the walk-throughs and the condition carry the model's names, marked as AI", async ({ page }) => {
    const base = await startReview(page);
    const walks = page.locator("section.ov-sec").first().locator(".dz-walks a");
    await expect(walks).toHaveCount(3);
    const titles = ["A write longer than 64 bytes", "A write that fits", "Setting up the UART"];
    for (const [i, t] of titles.entries()) await expect(walks.nth(i)).toHaveAttribute("aria-label", `Walk through: ${t}`);
    await expect(walks.locator(".ai-name")).toHaveCount(3);
    await expect(page.getByRole("heading", { name: /Writes that fit \(64 bytes or less\) · 5 changes still run$/ })).toBeVisible();
    await expect(page.getByRole("region", { name: "When the condition is false" }).locator("summary .ai-name")).toHaveCount(1);
    await walks.first().click();
    await expect(page).toHaveURL(new RegExp(`${base}/walk/W1$`));
    await expect(page.locator(".dz-walk h2 .ai-name")).toHaveText("Written by AI: A write longer than 64 bytes");
    await expect(page.locator(".dz-walk p.ai-text").first()).toContainText("It follows a long write from main into uart_send and back.");
    await expect(page.locator("aside.ws-outline .ws-row.walk[aria-current='page']"))
      .toHaveAttribute("aria-label", /^Walk through: A write longer than 64 bytes, 9 steps/);
  });
});

test.describe("the concerns table beside an open panel", () => {
  test.use({ baseURL: STRONG, viewport: { width: 1200, height: 900 } });

  test("stacks by the overview's own width, each cell labelled and still a cell (phase 2 minors 3, 4)", async ({ page }) => {
    await startReview(page);
    const section = page.getByRole("region", { name: "What it must get right" }), cells = section.locator("tbody tr").first().locator("td");
    const box = async (i: number) => (await cells.nth(i).boundingBox())!;
    expect((await box(1)).y).toBeLessThan((await box(0)).y + (await box(0)).height);       // side by side, the panel shut
    await section.locator("tbody tr").first().locator(".st-chip").click();
    await expect(page.locator(".cs")).toBeVisible();                                      // the check opens in the panel
    await expect.poll(async () => (await box(1)).y - ((await box(0)).y + (await box(0)).height)).toBeGreaterThanOrEqual(-1);
    await expect(cells.nth(1)).toHaveAttribute("data-label", "How the change does it");
    expect(await cells.nth(1).evaluate((e) => getComputedStyle(e, "::before").content)).toBe('"How the change does it"');
    await expect(section.getByRole("cell")).toHaveCount(12);
    await expect(section.getByRole("columnheader")).toHaveCount(4);
  });

  test("a check the design cites shows its chip though its kind is hidden, muted (phase 2 minor 7)", async ({ page }) => {
    // Confirm is hidden by default (the outline's "Showing: all but Confirm")
    await startReview(page);
    const chip = page.getByRole("region", { name: "What it must get right" }).locator("tbody tr").nth(2).locator(".st-chip");
    await expect(chip).toHaveCount(1);
    await expect(chip).toHaveClass(/\bconfirm\b/);
    await expect(chip).toHaveClass(/\bmuted\b/);
    await expect(page.locator(".ov-top .dz-verdict .st-chip")).not.toHaveClass(/\bmuted\b/);
  });
});

test.describe("the strong model's design text on a phone", () => {
  test.use({ baseURL: STRONG, viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
             deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("each concern's cells stack under one another, and nothing scrolls sideways", async ({ page }) => {
    await startReview(page);
    await page.getByRole("link", { name: "Go to the overview" }).click();
    const section = page.getByRole("region", { name: "What it must get right" }), cells = section.locator("tbody tr").first().locator("td");
    await expect(cells).toHaveCount(4);
    expect((await section.locator("thead").boundingBox())!.height).toBeLessThanOrEqual(1);   // seen by screen readers only
    await expect(section.getByRole("columnheader")).toHaveCount(4);
    const [a, b] = [await cells.nth(0).boundingBox(), await cells.nth(1).boundingBox()];
    expect(b!.y).toBeGreaterThanOrEqual(a!.y + a!.height - 1);
    expect(await sideways(page)).toBeLessThanOrEqual(0);
    await openFold(page, "Is the design right?");
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });

  test("a story's crumb names the concerns it answers, and each number scrolls the overview to its row", async ({ page }) => {
    await startReview(page);
    await page.getByRole("link", { name: "Go to the overview" }).click();
    const section = page.getByRole("region", { name: "What it must get right" });
    await expect(section.locator("tbody tr .dz-c-n")).toHaveText(["1", "2", "3"]);
    await section.locator("tbody tr").first().locator(".dz-c-where a").click();       // S1, which concerns 1 and 3 cite
    const crumb = page.locator(".st-crumb");
    await expect(crumb).toContainText("· answers concerns 1, 3");
    await crumb.getByRole("link", { name: "Go to concern 3 on the overview" }).click();
    await expect(page.locator("#concern-3")).toBeInViewport();
  });
});
