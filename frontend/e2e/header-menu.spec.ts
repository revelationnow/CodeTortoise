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

test.describe("a tablet", () => {
  test.use({ viewport: { width: 900, height: 900 } });
  test("the menu and its panels stay above the side panel that is open over the page", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}?open=${encodeURIComponent("file://fixture/driver/uart.c")}`);
    await expect(page.getByRole("complementary", { name: "Code: uart.c" })).toBeVisible();
    const onTop = (el: Element) => {                                      // the middle of it is what a click would hit
      const b = el.getBoundingClientRect(), hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
      return !!hit && el.contains(hit);
    };
    const menu = await reviewMenu(page);
    expect(await menu.evaluate(onTop)).toBe(true);
    await menu.getByRole("menuitem", { name: /^Stage notes/ }).click({ timeout: 5_000 });
    expect(await page.getByRole("dialog", { name: "Stage notes" }).evaluate(onTop)).toBe(true);
  });
});

test.describe("a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  const sideways = (el: Element) => el.scrollWidth - el.clientWidth;      // what a panel that scrolls sideways has to spare

  test("a long path in the drift panel wraps inside it instead of scrolling it sideways", async ({ page }) => {
    const base = await startReview(page);
    const path = "//depot/main/firmware/peripheral_drivers/uart_controller_with_a_long_descriptive_directory_name/uart_transmit_queue.c";
    await page.route("**/api/reviews/*/board", async (route) => {
      const res = await route.fetch(), j = await res.json();
      j.about.drift = [{ text: `${path} (base #3, workspace #2)`, kind: "behind", severity: "warn" }];
      await route.fulfill({ response: res, json: j });
    });
    await page.goto(base);
    await (await reviewMenu(page)).getByRole("menuitem", { name: "Workspace drift · 1" }).click();
    const drift = page.getByRole("dialog", { name: "Workspace drift" });
    await expect(drift).toContainText(path);
    expect(await drift.evaluate(sideways), "the drift panel scrolls sideways").toBeLessThanOrEqual(0);
  });

  test("a long word in a stage note wraps inside the panel instead of scrolling it sideways", async ({ page }) => {
    const base = await startReview(page);
    const word = "swarm_endpoint_https_models_example_com_v1_chat_completions_deployment_unbroken_name_1234567890";
    await page.route(/\/api\/reviews\/\d+$/, async (route) => {
      const res = await route.fetch(), j = await res.json();
      j.stages = j.stages.map((s: { name: string }) => (s.name === "swarm_read" ? { ...s, status: "failed", message: `Swarm is down: ${word}` } : s));
      await route.fulfill({ response: res, json: j });
    });
    await page.goto(base);
    await (await reviewMenu(page)).getByRole("menuitem", { name: /^Stage notes/ }).click();
    const notes = page.getByRole("dialog", { name: "Stage notes" });
    await expect(notes).toContainText(word);
    expect(await notes.evaluate(sideways), "the stage-notes panel scrolls sideways").toBeLessThanOrEqual(0);
  });
});
