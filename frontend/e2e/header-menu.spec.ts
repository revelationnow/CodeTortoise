import { expect, type Locator, type Page, test } from "@playwright/test";
import { openAiUsage, railReady, reviewMenu, startReview } from "./helpers";

const AI = "http://127.0.0.1:8798";      // e2e/serve-ai.sh: CodeTortoise with the fake model in e2e/fake_llm.py

/** The header's one row and its ⋯ menu (spec 2026-10-25-review-ui-redesign §2). */
test.use({ viewport: { width: 1440, height: 900 } });

/** Open uart.c's diff beside the page and start a comment thread on its new `return -2;` line; returns the thread, which
 * keeps its presses to itself. */
async function openThread(page: Page, base: string): Promise<Locator> {
  await page.goto(`${base}?open=${encodeURIComponent("file://fixture/driver/uart.c")}`);
  const file = page.getByRole("complementary", { name: "Code: uart.c" });
  await file.getByRole("button", { name: "Stacked" }).click();
  await file.locator(".bd-ln.a", { hasText: "return -2;" }).first().click();
  const thread = file.locator(".bd-thread");
  await expect(thread.getByPlaceholder("Leave a comment…")).toBeVisible();
  return thread;
}

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

test("Single-key shortcuts is a checkbox item after the help, on at first; a pick turns it off and returns to ⋯, the menu reopens showing it off, and a reload keeps it", async ({ page }) => {
  await startReview(page);
  const button = page.getByRole("button", { name: "Review menu" });
  const item = (menu: Locator) => menu.getByRole("menuitemcheckbox", { name: "Single-key shortcuts" });
  let menu = await reviewMenu(page);
  await expect(menu.locator('[role="menuitem"],[role="menuitemcheckbox"]'))
    .toHaveText([/^Stage notes · \d+$/, "How to read this page", "Single-key shortcuts✓", "Re-run"]);
  await expect(item(menu)).toHaveAttribute("aria-checked", "true");
  await expect(item(menu).locator(".rm-check"), "a ✓ shows it is on, for the eye only").toHaveText("✓");
  await expect(item(menu).locator(".rm-check")).toHaveAttribute("aria-hidden", "true");
  // useMenu starts a radio menu on its checked item; a checked checkbox item is no place to start
  await expect(menu.getByRole("menuitem").first(), "the menu opens on its first item, with the box checked").toBeFocused();
  await expect(item(menu)).not.toBeFocused();
  await page.keyboard.press("ArrowDown");                                 // Stage notes → How to read this page
  await page.keyboard.press("ArrowDown");                                 // → the switch: the arrow keys walk checkbox items too
  await expect(item(menu)).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(menu).toHaveCount(0);
  await expect(button, "a pick returns focus to ⋯").toBeFocused();
  menu = await reviewMenu(page);
  await expect(item(menu)).toHaveAttribute("aria-checked", "false");
  await expect(item(menu).locator(".rm-check")).toHaveText("");
  await expect(menu.getByRole("menuitem").first(), "and on its first item with the box unchecked").toBeFocused();
  await page.keyboard.press("Escape");
  await page.reload();
  await railReady(page);
  menu = await reviewMenu(page);
  await expect(item(menu), "a reload keeps it").toHaveAttribute("aria-checked", "false");
  await item(menu).click();                                               // and a click turns it on again
  await expect(menu).toHaveCount(0);
  await expect(button).toBeFocused();
  menu = await reviewMenu(page);
  await expect(item(menu)).toHaveAttribute("aria-checked", "true");
  await expect(item(menu).locator(".rm-check")).toHaveText("✓");
  await page.keyboard.press("Escape");
  await page.evaluate(() => window.localStorage.setItem("ct.ws.shortcuts", "false"));   // another tab switched it off
  menu = await reviewMenu(page);
  await expect(item(menu), "the menu shows what is stored each time it opens").toHaveAttribute("aria-checked", "false");
});

test("a press inside a code comment thread, which keeps its presses to itself, still closes the menu", async ({ page }) => {
  const thread = await openThread(page, await startReview(page));
  const menu = await reviewMenu(page);
  await thread.click({ position: { x: 4, y: 6 } });                      // its padding: nothing there takes focus
  await expect(menu).toHaveCount(0);
});

test("a press inside a code comment thread, which keeps its presses to itself, still closes a panel the menu opened", async ({ page }) => {
  const thread = await openThread(page, await startReview(page));
  await (await reviewMenu(page)).getByRole("menuitem", { name: "How to read this page" }).click();
  const help = page.getByRole("dialog", { name: "How to read this page" });
  await expect(help).toBeVisible();
  await thread.click({ position: { x: 4, y: 6 } });
  await expect(help).toHaveCount(0);
});

test("a re-run that fails says so in a panel under the header, and nothing throws; Escape closes it and returns to ⋯", async ({ page }) => {
  await startReview(page);
  const thrown: string[] = [];
  page.on("pageerror", (e) => thrown.push(e.message));
  await page.route("**/api/reviews/*/rerun*", (route) => route.fulfill({ status: 500, json: { detail: "The runner is not accepting reviews" } }));
  await (await reviewMenu(page)).getByRole("menuitem", { name: "Re-run", exact: true }).click();
  const failed = page.getByRole("dialog", { name: "Re-run failed" });
  await expect(failed).toContainText("The runner is not accepting reviews");
  expect(thrown, "the rejected request is handled, not thrown").toEqual([]);
  await page.keyboard.press("Escape");
  await expect(failed).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Review menu/ })).toBeFocused();
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

  test.describe("with the outline dragged wide", () => {
    test.use({ viewport: { width: 700, height: 900 } });
    test("the menu stays above the outline drawer that is open over the page", async ({ page }) => {
      await page.addInitScript(() => localStorage.setItem("ct.ws.railW", "600"));   // dragged wide, the drawer reaches under the menu
      await startReview(page);
      const drawer = page.locator("aside.ws-outline");
      await page.getByRole("button", { name: "Review contents", exact: true }).click();
      await expect.poll(async () => (await drawer.boundingBox())!.x, { message: "the drawer has slid in" }).toBe(0);
      const menu = await reviewMenu(page);
      const m = await menu.evaluate((el) => {                                // the middle of it is what a click would hit
        const b = el.getBoundingClientRect(), x = b.left + b.width / 2, y = b.top + b.height / 2, hit = document.elementFromPoint(x, y);
        return { x, drawerEnd: document.querySelector("aside.ws-outline")!.getBoundingClientRect().right, inside: !!hit && el.contains(hit) };
      });
      expect(m.drawerEnd, "the drawer reaches under the middle of the menu, so the stacking is tested").toBeGreaterThan(m.x);
      expect(m.inside, "the menu is above the drawer").toBe(true);
    });
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
    test.use({ baseURL: AI });

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

/** The AI usage panel (spec 2026-10-25-review-ui-redesign §2.2), opened from ⋯ or from the pill that shows near the budget. */
test.describe("the AI usage panel", () => {
  test.use({ baseURL: AI, viewport: { width: 1280, height: 800 } });
  const pill = (page: Page) => page.getByRole("button", { name: /^AI \d+\/\d+$/ });
  const panel = (page: Page) => page.getByRole("dialog", { name: "AI usage" });
  /** The review has used 90% of its calls, so the header shows the pill (spec §2.1), until `near.on` is set false. */
  const nearTheBudget = async (page: Page) => {
    const near = { on: true };
    await page.route("**/api/reviews/*/ai", async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      const res = await route.fetch(), j = await res.json();
      await route.fulfill({ response: res, json: near.on ? { ...j, used: Math.ceil(j.budget * 0.9) } : j });
    });
    return near;
  };

  test("opened from ⋯ it takes focus; Escape and Close give it back to ⋯", async ({ page }) => {
    await startReview(page);
    const button = page.getByRole("button", { name: /^Review menu/ }), usage = panel(page);
    await openAiUsage(page);
    await expect(usage, "opening moves focus into the panel").toBeFocused();
    await page.keyboard.press("Escape");
    await expect(usage).toHaveCount(0);
    await expect(button, "Escape returns focus to ⋯").toBeFocused();
    await openAiUsage(page);
    await expect(usage).toBeFocused();
    await usage.getByRole("button", { name: "Close" }).click();
    await expect(usage).toHaveCount(0);
    await expect(button, "Close returns focus to ⋯").toBeFocused();
  });

  test("opened from the pill it takes focus; Escape and Close give it back to the pill", async ({ page }) => {
    await nearTheBudget(page);
    await startReview(page);
    const usage = panel(page);
    await pill(page).click();
    await expect(usage, "opening moves focus into the panel").toBeFocused();
    await page.keyboard.press("Escape");
    await expect(usage).toHaveCount(0);
    await expect(pill(page), "Escape returns focus to the pill").toBeFocused();
    await pill(page).click();
    await expect(usage).toBeFocused();
    await usage.getByRole("button", { name: "Close" }).click();
    await expect(usage).toHaveCount(0);
    await expect(pill(page), "Close returns focus to the pill").toBeFocused();
  });

  test("when the budget is raised so far that the pill goes, Escape hands focus to ⋯ instead of to nothing", async ({ page }) => {
    const near = await nearTheBudget(page);
    await startReview(page);
    const usage = panel(page);
    await pill(page).click();
    await expect(usage).toBeFocused();
    near.on = false;                                                     // the next load of the review's AI state is far from its limit
    await usage.getByRole("button", { name: "Raise budget", exact: true }).click();
    await expect(pill(page)).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(usage).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Review menu/ }), "the pill is gone, so ⋯ has focus").toBeFocused();
  });

  test("J, K and F stay off the page's Flows tab while the panel has focus", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/s/S1`);
    const rows = page.locator(".fl-toggle");
    await expect(rows).toHaveCount(2);
    await rows.first().click();                                          // the row J, K and F act from
    const usage = await openAiUsage(page);
    await expect(usage).toBeFocused();
    for (const key of ["j", "k", "f"]) {
      await page.keyboard.press(key);
      await expect(usage, `${key} leaves focus in the panel`).toBeFocused();
    }
    await expect(page.locator(".fl-toggle:focus"), "no row took focus").toHaveCount(0);
  });

  test("a press outside it closes it", async ({ page }) => {
    await startReview(page);
    const usage = await openAiUsage(page);
    await page.getByRole("region", { name: "Centre" }).click({ position: { x: 5, y: 5 } });
    await expect(usage).toHaveCount(0);
  });

  test("a press inside a code comment thread, which keeps its presses to itself, still closes it", async ({ page }) => {
    const thread = await openThread(page, await startReview(page));
    const usage = await openAiUsage(page);
    await thread.click({ position: { x: 4, y: 6 } });
    await expect(usage).toHaveCount(0);
  });

  test("it sits under the header's right end, whichever opened it", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("ct.ws.headH", "120"));   // dragged taller: under the header is no fixed place
    await nearTheBudget(page);
    await startReview(page);
    const usage = panel(page), head = page.locator(".ws-headbox");
    const placed = async (how: string) => {
      await expect(usage).toBeVisible();
      const at = (await usage.boundingBox())!, bar = (await head.boundingBox())!;
      const gap = at.y - (bar.y + bar.height);
      expect(gap, `from ${how}, its top is under the header's bottom`).toBeGreaterThanOrEqual(0);
      expect(gap, `from ${how}, its top is at the header's bottom`).toBeLessThanOrEqual(8);
      expect(1280 - (at.x + at.width), `from ${how}, its right edge is 16px in from the window's`).toBeCloseTo(16, 0);
    };
    await openAiUsage(page);
    await placed("⋯");
    await page.keyboard.press("Escape");
    await pill(page).click();
    await placed("the pill");
  });

  test.describe("on a phone", () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test("the All calls table fits inside the panel instead of running past it, whatever its cells hold", async ({ page }) => {
      await page.route("**/api/reviews/*/ai/calls", async (route) => {         // the fixture's calls, and one whose cells hold long names
        const res = await route.fetch(), calls = await res.json();
        const long = { ...calls[0], id: 9001, user: "a-reviewer-with-a-long-user-name", target: "S12.flow3_with_a_long_target_name",
                       model: "example-model-with-a-long-name-2025-09-29", prompt_tokens: 123456, completion_tokens: 7890, outcome: "refused", requests: 3 };
        await route.fulfill({ response: res, json: [...calls, long] });
      });
      await startReview(page);
      const usage = await openAiUsage(page);
      await usage.getByText(/^All calls/).click();
      await expect(usage.locator(".ai-calls tbody tr").nth(1), "the fixture's calls, and the long one").toBeVisible();
      const m = await usage.evaluate((el) => {
        const own = getComputedStyle(el), box = el.getBoundingClientRect();
        return { table: el.querySelector(".ai-calls")!.getBoundingClientRect().right,
                 content: box.left + el.clientLeft + el.clientWidth - parseFloat(own.paddingRight), sideways: el.scrollWidth - el.clientWidth,
                 spilling: [...el.querySelectorAll<HTMLElement>(".ai-calls th, .ai-calls td")].filter((c) => c.scrollWidth > c.clientWidth)
                   .map((c) => c.textContent) };
      });
      expect(m.table, "the table ends inside the panel's padding").toBeLessThanOrEqual(m.content + 0.5);
      expect(m.sideways, "the panel scrolls sideways").toBeLessThanOrEqual(0);
      expect(m.spilling, "cells whose text runs out of them into the next").toEqual([]);
      await expect(usage.locator(".ai-calls"), "a smaller font on a phone").toHaveCSS("font-size", "11px");
    });
  });
});

test.describe("a window 320px tall", () => {
  test.use({ baseURL: AI, viewport: { width: 1280, height: 320 } });

  test("the ⋯ menu ends 16px above the window's bottom and scrolls inside itself to its end", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("ct.ws.headH", "200"));   // dragged taller: the menu sits lower
    await startReview(page);
    const menu = await reviewMenu(page);
    await fitsTheWindow(menu, "⋯ menu");
    const box = (await menu.boundingBox())!;
    expect(box.y + box.height, "the menu ends 16px above the window's bottom").toBeLessThanOrEqual(320 - 16 + 0.5);
  });
});
