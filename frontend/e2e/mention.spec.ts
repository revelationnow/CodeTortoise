import { expect, type Locator, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

const AI = "http://127.0.0.1:8798";      // e2e/serve-ai.sh: CodeTortoise with the fake model in e2e/fake_llm.py

/** Open uart.c in the file viewer and start a comment on its new `return -2;` line. */
async function commentOnReturn(page: Page): Promise<{ viewer: Locator; box: Locator }> {
  await page.locator(".bd-about .tree .file", { hasText: "uart.c" }).first().click();
  const viewer = page.locator(".bd-viewer");
  await viewer.getByRole("button", { name: "Stacked" }).click();
  await viewer.locator(".bd-ln.a", { hasText: "return -2;" }).first().click();
  return { viewer, box: viewer.getByPlaceholder("Leave a comment…") };
}

test.describe("with an AI", () => {
  test.use({ baseURL: AI });

  test("the @ menu asks tortoise, which reads code and answers in the thread", async ({ page }) => {
    await startReview(page);
    const { viewer, box } = await commentOnReturn(page);
    await box.fill("Who handles this? ");
    await box.pressSequentially("@");
    const menu = viewer.getByRole("listbox", { name: "Mention" });
    await expect(menu.getByRole("option")).toHaveText([/@tortoise.*up to 6 AI calls/, /@demo/]);
    await box.press("Escape");                                            // Esc closes it
    await expect(menu).toBeHidden();
    await box.press("Backspace");                                         // a new @ opens it again
    await box.pressSequentially("@");
    await expect(menu).toBeVisible();
    await box.press("Escape");
    await box.pressSequentially(" @t");                                   // typing narrows it; Enter inserts
    await expect(menu.getByRole("option")).toHaveCount(1);
    await box.press("Enter");
    await expect(box).toHaveValue("Who handles this? @ @tortoise ");
    await box.pressSequentially("which callers see the -2?");
    await viewer.getByRole("button", { name: "Comment", exact: true }).click();

    const reply = viewer.locator(".comment.ai");
    await expect(reply).toContainText("logger_flush drops the -2 that uart_send now returns.", { timeout: 30_000 });
    await expect(reply).toContainText("read: callers of uart_send");
    await expect(reply.locator(".ai-label")).toHaveText("AI");
    await expect(reply.getByRole("button", { name: "edit" })).toHaveCount(0);   // tortoise replies can't be edited
  });

  test("when the review's budget is spent, tortoise says so and the owner can raise it from the reply", async ({ page }) => {
    await startReview(page);
    await page.getByRole("button", { name: /^AI \d+\/200$/ }).click();
    const usage = page.getByRole("dialog", { name: "AI usage" });
    await usage.getByLabel("New budget").fill("2");                      // the up-front pass used 2: summary and 1 flow
    await usage.getByRole("button", { name: "Raise budget" }).click();
    await expect(page.getByRole("button", { name: "AI 2/2" })).toBeVisible();
    await usage.getByRole("button", { name: "Close" }).click();
    const { viewer, box } = await commentOnReturn(page);
    await box.fill("@tortoise does this leak?");
    await viewer.getByRole("button", { name: "Comment", exact: true }).click();
    const reply = viewer.locator(".comment.ai");
    await expect(reply).toContainText("I couldn't answer: this review has used its 2 AI calls; the owner can raise it.");
    await reply.getByRole("button", { name: "Raise budget" }).click();
    await expect(page.getByRole("dialog", { name: "AI usage" })).toBeVisible();
  });
});

test.describe("without an AI", () => {
  test("@tortoise is greyed out with the reason, and there are no AI controls", async ({ page }) => {
    await startReview(page);
    await expect(page.getByRole("button", { name: /^AI \d+/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /✦/ })).toHaveCount(0);
    const { viewer, box } = await commentOnReturn(page);
    await box.pressSequentially("@");
    const first = viewer.getByRole("listbox", { name: "Mention" }).getByRole("option").first();
    await expect(first).toContainText("no AI is configured for CodeTortoise");
    await expect(first).toHaveAttribute("aria-disabled", "true");
    await box.press("Enter");                                             // nothing is inserted
    await expect(box).toHaveValue("@");
  });
});
