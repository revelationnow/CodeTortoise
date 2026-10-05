import { expect, type Locator, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

const AI = "http://127.0.0.1:8798";      // e2e/serve-ai.sh: CodeTortoise with the fake model in e2e/fake_llm.py

/** Open uart.c's diff in the detail panel and start a comment on its new `return -2;` line. */
async function commentOnReturn(page: Page): Promise<{ viewer: Locator; box: Locator }> {
  await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
  await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
  const viewer = page.getByRole("complementary", { name: "Code: uart.c" });
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
    await expect(menu.getByRole("option")).toHaveText([/@tortoise.*1 AI call, reading code for up to 10 rounds/, /@demo/]);
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

  test("Ask… on an explain button puts the question to tortoise in a thread on that finding, story, flow or file", async ({ page }) => {
    const base = await startReview(page);
    const ask = async (where: Locator, question: string) => {
      await where.getByRole("button", { name: "Ask…" }).first().click();
      await where.getByLabel("What should the AI explain?").fill(question);
      await where.getByRole("button", { name: "Ask", exact: true }).click();
    };
    const answer = "logger_flush drops the -2 that uart_send now returns.";

    await page.goto(`${base}/f/F1`);
    const finding = page.locator(".ws-finding");
    await ask(finding.locator("#ws-ai").locator(".."), "why is this risky for the logger?");
    await expect(finding.locator(".comment", { hasText: "@tortoise why is this risky for the logger?" })).toBeVisible();
    await expect(finding.locator(".comment.ai")).toContainText(answer, { timeout: 30_000 });

    await page.goto(`${base}/s/S1`);
    await ask(page.locator(".ws-story-head"), "what does this story change for callers?");
    const talk = page.getByRole("region", { name: "Questions and comments" });
    await expect(talk.locator(".comment", { hasText: "what does this story change for callers?" })).toBeVisible();
    await expect(talk.locator(".comment.ai")).toContainText(answer, { timeout: 30_000 });

    const strip = page.getByRole("region", { name: "Flow" });
    await strip.getByRole("button", { name: "Next flow" }).click();          // flow 1's text is the story's summary
    await ask(strip, "is the new writer safe?");
    await expect(strip.locator(".comment.ai")).toContainText(answer, { timeout: 30_000 });

    await page.goto(`${base}?open=${encodeURIComponent("file://fixture/driver/uart.c")}`);
    const file = page.getByRole("complementary", { name: "Code: uart.c" });
    await ask(file.locator(".ws-file-tools"), "what changed in error handling?");
    await expect(file.locator(".ws-file-talk .comment.ai")).toContainText(answer, { timeout: 30_000 });
  });

  test("when the review's budget is spent, tortoise says so and the owner can raise it from the reply", async ({ page }) => {
    await startReview(page);
    await page.getByRole("button", { name: /^AI \d+\/200$/ }).click();
    const usage = page.getByRole("dialog", { name: "AI usage" });
    await usage.getByLabel("New budget").fill("3");                      // the up-front pass used 3: summary, 1 flow, 1 finding
    await usage.getByRole("button", { name: "Raise budget" }).click();
    await expect(page.getByRole("button", { name: "AI 3/3" })).toBeVisible();
    await usage.getByRole("button", { name: "Close" }).click();
    const { viewer, box } = await commentOnReturn(page);
    await box.fill("@tortoise does this leak?");
    await viewer.getByRole("button", { name: "Comment", exact: true }).click();
    const reply = viewer.locator(".comment.ai");
    await expect(reply).toContainText("I couldn't answer: this review has used its 3 AI calls; the owner can raise it.");
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
