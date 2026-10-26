import { expect, test } from "@playwright/test";
import { reviewMenu, startReview } from "./helpers";

/** The header's one row and its ⋯ menu (spec 2026-10-25-review-ui-redesign §2). */
test.use({ viewport: { width: 1440, height: 900 } });

test("the header keeps one quiet row; the rest is in the review menu, which the keyboard walks", async ({ page }) => {
  await startReview(page);
  const head = page.locator(".ws-head");
  await expect(head.locator(".ct-headline")).toHaveText("Medium risk");
  await expect(head.getByRole("button", { name: "Re-run" })).toHaveCount(0);
  await expect(head.getByRole("button", { name: "How to read this page" })).toHaveCount(0);
  await expect(head.locator(".bd-notes")).toHaveCount(0);
  const button = page.getByRole("button", { name: "Review menu" });           // the demo: no drift, no failed stage
  await expect(button.locator(".rm-dot")).toHaveCount(0);
  const menu = await reviewMenu(page);
  await expect(button).toHaveAttribute("aria-expanded", "true");
  await expect(menu.getByRole("menuitem")).toHaveText([/^Stage notes · \d+$/, "How to read this page", "Re-run"]);
  await expect(menu.getByRole("menuitem").first()).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(menu.getByRole("menuitem", { name: "How to read this page" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await expect(button).toBeFocused();
  await (await reviewMenu(page)).getByRole("menuitem", { name: /^Stage notes/ }).click();
  const notes = page.getByRole("dialog", { name: "Stage notes" });
  await expect(notes).toContainText("swarm_read");
  await page.getByRole("region", { name: "Centre" }).click({ position: { x: 5, y: 5 } });   // a press outside closes it
  await expect(notes).toHaveCount(0);
});

test("a drifted workspace or a failed stage lights a dot on the menu and says why in its name", async ({ page }) => {
  const base = await startReview(page);
  await page.route("**/api/reviews/*/board", async (route) => {
    const res = await route.fetch(), j = await res.json();
    j.about.drift = [{ text: "//fixture/driver/uart.c (base #3, workspace #2)", kind: "behind", severity: "warn" }];
    await route.fulfill({ response: res, json: j });
  });
  await page.route(/\/api\/reviews\/\d+$/, async (route) => {
    const res = await route.fetch(), j = await res.json();
    j.stages = j.stages.map((s: { name: string }) => (s.name === "swarm_read" ? { ...s, status: "failed", message: "Swarm is down" } : s));
    await route.fulfill({ response: res, json: j });
  });
  await page.goto(base);
  const button = page.getByRole("button", { name: "Review menu (workspace drift, a stage failed)" });
  await expect(button.locator(".rm-dot")).toBeVisible();
  const menu = await reviewMenu(page);
  await menu.getByRole("menuitem", { name: "Workspace drift · 1" }).click();
  const drift = page.getByRole("dialog", { name: "Workspace drift" });
  await expect(drift).toContainText("//fixture/driver/uart.c (base #3, workspace #2)");
  await page.keyboard.press("Escape");
  await expect(drift).toHaveCount(0);
  await expect(button).toBeFocused();
});

test("the menu hangs 16px in from the screen's edge even when the header ends short of it, as with a wide scrollbar", async ({ page }) => {
  await startReview(page);
  await page.addStyleTag({ content: ".ws-headbox { margin-right: 40px; }" });     // the header scrolls, so its edge is inside the screen's
  const box = (await (await reviewMenu(page)).boundingBox())!;
  expect(box.x + box.width).toBeCloseTo(1440 - 16, 0);                              // fixed to the screen: no container clips it
});
