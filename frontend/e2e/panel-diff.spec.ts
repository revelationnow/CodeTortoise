import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

test("the change panel keeps changelists in their own tab with expandable descriptions", async ({ page }) => {
  await startReview(page);
  const panel = page.locator(".bd-about");
  await expect(panel.getByRole("tab", { name: "Summary" })).toHaveAttribute("aria-selected", "true");
  await expect(panel.getByText("Files in this change")).toBeVisible();
  await expect(panel.locator(".cl")).toHaveCount(0);                            // not on the summary any more
  await panel.getByRole("tab", { name: "Changelists (2)" }).click();
  const cl = panel.locator(".cl", { hasText: "CL 101" });
  await expect(cl.locator(".first")).toBeVisible();
  await expect(cl.locator(".desc")).toHaveCount(0);
  await cl.getByRole("button", { name: /CL 101/ }).click();
  await expect(cl.locator(".desc")).toBeVisible();
  await page.reload();                                                          // the tab is remembered per review
  await expect(page.locator(".bd-about").getByRole("tab", { name: "Changelists (2)" })).toHaveAttribute("aria-selected", "true");
});

test("a changed file opens on its changes, folds the rest, and grows on request", async ({ page }) => {
  await startReview(page);
  await page.locator(".bd-about .tree .file", { hasText: "regs.h" }).first().click();
  const sec = page.locator('.bd-viewer .fsec[data-path="//fixture/include/hal/regs.h"]');
  await expect(sec.getByRole("button", { name: "Changes" })).toHaveClass(/\bon\b/);
  const gap = sec.locator(".bd-gap").first();
  await expect(gap).toContainText("9 lines hidden");
  await expect(sec.locator('[data-n="1"]')).toHaveCount(0);
  await gap.getByRole("button", { name: "▲ 9 more" }).click();
  await expect(sec.locator('[data-n="1"]')).toBeVisible();
  await expect(sec.locator(".bd-gap")).toHaveCount(0);
  await sec.getByRole("button", { name: "Full file" }).click();
  await expect(sec.locator('[data-n="15"]')).toBeVisible();
  await page.reload();                                                          // the view is remembered
  await page.locator(".bd-about .tree .file", { hasText: "regs.h" }).first().click();
  await expect(page.locator('.bd-viewer .fsec[data-path="//fixture/include/hal/regs.h"]')
    .getByRole("button", { name: "Full file" })).toHaveClass(/\bon\b/);
});

test("switching between changes and the full file keeps your place", async ({ page }) => {
  await startReview(page);
  await page.locator(".bd-about .tree .file", { hasText: "regs.h" }).first().click();
  const sec = page.locator('.bd-viewer .fsec[data-path="//fixture/include/hal/regs.h"]');
  await expect(sec.locator('[data-n="3"]')).toHaveCount(0);                    // folded in the changes view
  await sec.getByRole("button", { name: "Full file" }).click();
  const line = sec.locator('[data-n="3"]');
  const box = page.locator(".bd-viewer .files");
  const at = async () => (await line.evaluate((el) => el.getBoundingClientRect().top)) - (await box.evaluate((el) => el.getBoundingClientRect().top));
  await box.evaluate((el, y) => { el.scrollTop += y; }, await at());           // line 3 at the top of the viewer
  const before = await at();
  await sec.getByRole("button", { name: "Changes" }).click();
  await expect(line).toBeVisible();                                             // its folded run opened around it
  expect(Math.abs((await at()) - before)).toBeLessThan(4);                      // and it stayed where it was
});

test("opening a file at a folded line shows that line", async ({ page }) => {
  await startReview(page);
  await page.locator(".bd-about .fx-fn", { hasText: "uart_init" }).click();   // uart_init: line 8, outside the hunks
  const sec = page.locator('.bd-viewer .fsec[data-path="//fixture/driver/uart.c"]');
  await expect(sec.locator('.focus[data-n="8"]')).toBeVisible();
});

test("one changelist's diff, with comments made on it", async ({ page }) => {
  await startReview(page);
  await page.locator(".bd-about .tree .file", { hasText: "uart.c" }).first().click();
  const sec = page.locator('.bd-viewer .fsec[data-path="//fixture/driver/uart.c"]');
  await expect(sec.locator(".hd")).toContainText("edit");                     // action and base revision
  await page.locator(".bd-viewer").getByRole("button", { name: "Stacked" }).click();
  await sec.getByLabel("Changelist").selectOption("101");
  const added = sec.locator(".bd-ln.a").first();
  await added.click();
  await sec.locator("textarea").fill("only in CL 101");
  await sec.getByRole("button", { name: "Comment", exact: true }).click();
  await expect(sec.getByText("only in CL 101")).toBeVisible();
  await sec.getByLabel("Changelist").selectOption("all");
  await expect(sec.getByText("only in CL 101")).toHaveCount(0);
  await sec.getByLabel("Changelist").selectOption("101");
  await expect(sec.getByText("only in CL 101")).toBeVisible();
});

test("the old files page opens the board", async ({ page }) => {
  await startReview(page);
  const id = page.url().match(/\/r\/(\d+)/)![1];
  await expect(page.getByRole("link", { name: /^Files/ })).toHaveCount(0);
  await page.goto(`/r/${id}/files`);
  await expect(page).toHaveURL(new RegExp(`/r/${id}$`));
  await expect(page.locator(".bd-node").first()).toBeVisible();
});
