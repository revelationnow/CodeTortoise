import { expect, type Locator, test } from "@playwright/test";
import { openAiUsage, reviewMenu, startReview } from "./helpers";

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

test("Tab out of the menu closes it and leaves focus where Tab took it; Shift+Tab back to ⋯ closes it too; Escape still returns to ⋯", async ({ page }) => {
  await startReview(page);
  const button = page.getByRole("button", { name: "Review menu" });
  const menu = await reviewMenu(page);
  await expect(menu.getByRole("menuitem").first()).toBeFocused();
  for (let i = 0; i < 6 && await menu.count(); i++) await page.keyboard.press("Tab");
  await expect(menu).toHaveCount(0);
  await expect(button).toHaveAttribute("aria-expanded", "false");
  const at = await page.evaluate(() => ({ body: document.activeElement === document.body, menu: !!document.activeElement?.closest(".rm") }));
  expect(at, "focus went on to the page, and was not pulled back to ⋯").toEqual({ body: false, menu: false });
  await reviewMenu(page);
  await page.keyboard.press("Shift+Tab");                                // from the first item back to ⋯
  await expect(button).toBeFocused();
  await expect(menu).toHaveCount(0);
  await reviewMenu(page);
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await expect(button).toBeFocused();
});

test("a press inside a code comment thread, which keeps its presses to itself, still closes the menu", async ({ page }) => {
  const base = await startReview(page);
  await page.goto(`${base}?open=${encodeURIComponent("file://fixture/driver/uart.c")}`);
  const file = page.getByRole("complementary", { name: "Code: uart.c" });
  await file.getByRole("button", { name: "Stacked" }).click();
  await file.locator(".bd-ln.a", { hasText: "return -2;" }).first().click();
  const thread = file.locator(".bd-thread");
  await expect(thread.getByPlaceholder("Leave a comment…")).toBeVisible();
  const menu = await reviewMenu(page);
  await thread.click({ position: { x: 4, y: 6 } });                      // its padding: nothing there takes focus
  await expect(menu).toHaveCount(0);
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

/** A panel under the header ends inside the window, and scrolled to its end it shows the end of what it holds there. */
async function fitsTheWindow(panel: Locator, what: string) {
  await expect(panel).toBeVisible();
  const m = await panel.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
    return { bottom: el.getBoundingClientRect().bottom, last: el.lastElementChild!.getBoundingClientRect().bottom,
             scrolls: el.scrollHeight > el.clientHeight, window: window.innerHeight };
  });
  expect(m.scrolls, `the ${what} panel holds more than fits, so it scrolls`).toBe(true);
  expect(m.bottom, `the ${what} panel ends inside the window`).toBeLessThanOrEqual(m.window);
  expect(m.last, `scrolled to its end, the ${what} panel shows the end of what it holds`).toBeLessThanOrEqual(Math.min(m.bottom, m.window));
}

test.describe("a short window", () => {
  test.use({ viewport: { width: 1440, height: 520 } });

  test("the help, drift and stage-notes panels end inside the window and scroll inside themselves to their ends", async ({ page }) => {
    const base = await startReview(page);
    await page.route("**/api/reviews/*/board", async (route) => {
      const res = await route.fetch(), j = await res.json();
      j.about.drift = Array.from({ length: 40 }, (_, i) => ({ text: `//fixture/driver/file_${i}.c (base #3, workspace #2)`, kind: "behind", severity: "warn" }));
      await route.fulfill({ response: res, json: j });
    });
    await page.route(/\/api\/reviews\/\d+$/, async (route) => {
      const res = await route.fetch(), j = await res.json();
      j.stages = j.stages.map((s: { name: string }) => ({ ...s, status: "failed", message: `${s.name} failed. `.repeat(12) }));
      await route.fulfill({ response: res, json: j });
    });
    await page.goto(base);
    for (const [item, name] of [[/^How to read this page$/, "How to read this page"], [/^Workspace drift · 40$/, "Workspace drift"],
                                [/^Stage notes · \d+$/, "Stage notes"]] as const) {
      await (await reviewMenu(page)).getByRole("menuitem", { name: item }).click();
      await fitsTheWindow(page.getByRole("dialog", { name }), name);
      await page.keyboard.press("Escape");
    }
  });

  test.describe("with an AI and a tall header", () => {
    test.use({ baseURL: "http://127.0.0.1:8798" });

    test("the AI usage panel ends inside the window and scrolls inside itself to its end", async ({ page }) => {
      await page.addInitScript(() => localStorage.setItem("ct.ws.headH", "200"));   // dragged taller: the panels sit lower
      await startReview(page);
      const usage = await openAiUsage(page);
      await usage.getByText(/^All calls/).click();
      await expect(usage.locator(".ai-calls tbody tr").first()).toBeVisible();
      await fitsTheWindow(usage, "AI usage");
      await page.keyboard.press("Escape");
      await (await reviewMenu(page)).getByRole("menuitem", { name: "How to read this page" }).click();
      await fitsTheWindow(page.getByRole("dialog", { name: "How to read this page" }), "How to read this page");
    });
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
