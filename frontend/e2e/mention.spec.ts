import { expect, type Locator, type Page, test } from "@playwright/test";
import { AI, commentOnReturn, contrast, explainItem, hold, openAiUsage, openIndex, reviewMenu, startReview } from "./helpers";

/** Open uart.c's diff in the detail panel from the Index's Files and start a comment on its new `return -2;` line. */
async function commentFromIndex(page: Page) {
  await openIndex(page, "Files");
  await page.getByRole("link", { name: "Open uart.c's diff" }).click();
  return commentOnReturn(page);
}

test.describe("with an AI", () => {
  test.use({ baseURL: AI });

  test("the @ menu asks tortoise, which reads code and answers in the thread", async ({ page }) => {
    await startReview(page);
    const { viewer, box } = await commentFromIndex(page);
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
    await expect(reply.locator(".comment-body")).toHaveClass(/\bai-text\b/);
    await expect(reply.locator(".ai-label")).toHaveCount(0);
    await expect(reply.getByRole("button", { name: "edit" })).toHaveCount(0);   // tortoise replies can't be edited
  });

  test("Ask a question… in an Explain menu puts the question to tortoise in a thread on that finding, story, flow or file", async ({ page }) => {
    const base = await startReview(page);
    const ask = async (where: Locator, question: string) => {
      await explainItem(where, "Ask a question…");
      await where.getByLabel("What should the AI explain?").fill(question);
      await where.getByRole("button", { name: "Ask", exact: true }).click();
      await expect(where.getByRole("button", { name: /^(Explain|Summarise)$/ }).first(), "the question box is gone: focus is back on the button").toBeFocused();
    };
    const answer = "logger_flush drops the -2 that uart_send now returns.";

    await page.goto(`${base}/f/F1?details=1`);
    const finding = page.locator(".ws-finding");
    await ask(finding.locator("#ws-ai").locator(".."), "why is this risky for the logger?");
    await expect(finding.locator(".comment", { hasText: "@tortoise why is this risky for the logger?" })).toBeVisible();
    await expect(finding.locator(".comment.ai")).toContainText(answer, { timeout: 30_000 });

    await page.goto(`${base}/s/S1`);
    await ask(page.locator(".ws-story-head"), "what does this story change for callers?");
    await page.getByRole("navigation", { name: "Story sections" }).getByRole("link", { name: /^Talk/ }).click();
    const talk = page.getByRole("region", { name: "Questions and comments" });
    await expect(talk.locator(".comment", { hasText: "what does this story change for callers?" })).toBeVisible();
    await expect(talk.locator(".comment.ai")).toContainText(answer, { timeout: 30_000 });

    await page.goto(`${base}/s/S1?view=graph`);                              // a story's flows are on its graph
    const strip = page.getByRole("region", { name: "Flow" });
    await strip.getByRole("button", { name: "Next flow" }).click();
    await ask(strip, "is the new writer safe?");
    await expect(strip.locator(".comment.ai")).toContainText(answer, { timeout: 30_000 });

    await page.goto(`${base}?open=${encodeURIComponent("file://fixture/driver/uart.c")}`);
    const file = page.getByRole("complementary", { name: "Code: uart.c" });
    await ask(file.locator(".ws-file-tools"), "what changed in error handling?");
    await expect(file.locator(".ws-file-talk .comment.ai")).toContainText(answer, { timeout: 30_000 });
  });

  test("a sent question takes focus back to the Explain button only if the reader has not moved it meanwhile", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    await page.goto(`${base}/s/S1?view=graph`);
    const strip = page.getByRole("region", { name: "Flow" });
    const explain = strip.getByRole("button", { name: "Explain", exact: true }), next = strip.getByRole("button", { name: "Next flow" });
    const box = strip.getByLabel("What should the AI explain?");
    /** Ask with the server's answer held back, run `meanwhile` while the question is on its way, then let the answer land. */
    const askWhile = async (question: string, meanwhile: () => Promise<unknown>) => {
      const answer = await hold(page, `**/api/reviews/${rid}/comments`);
      await explainItem(strip, "Ask a question…");
      await box.fill(question);
      await strip.getByRole("button", { name: "Ask", exact: true }).click();
      await answer.held;
      await meanwhile();
      answer.release();
      await expect(strip.getByText("Asked: the answer comes in this item's thread.")).toBeVisible();   // landed: the box is shut
      await expect(box).toHaveCount(0);
    };
    await askWhile("is the new writer safe?", () => next.focus());                   // the reader moved to another control…
    await expect(next, "…and keeps it").toBeFocused();
    await expect(explain).not.toBeFocused();
    await askWhile("and the other flow?", () => page.evaluate(() => (document.activeElement as HTMLElement).blur()));   // …or focus fell to the page
    await expect(explain, "focus that fell to the page goes back to the button").toBeFocused();
  });

  test("a question the server refuses shows its error at once, beside the open box, which keeps the question to send again", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    await page.goto(`${base}/s/S1?view=graph`);
    const strip = page.getByRole("region", { name: "Flow" });
    const box = strip.getByLabel("What should the AI explain?");
    const ask = strip.locator(".ai-ask", { has: page.getByLabel("What should the AI explain?") });   // the Explain ▾ widget that holds the open box
    // a refusal with no words in it: what the page has to go on when the status line is empty too, as over HTTP/2
    await page.route(`**/api/reviews/${rid}/comments`, (route) =>
      route.request().method() === "POST" ? route.fulfill({ status: 500, json: { detail: "" } }) : route.continue());
    await explainItem(strip, "Ask a question…");
    await box.fill("is the new writer safe?");
    await strip.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(ask.getByRole("alert"), "told while the box is still open, beside it").toHaveText("The question could not be sent.");
    await expect(box, "the box stays open").toBeVisible();
    await expect(box, "…with the question in it, to send again").toHaveValue("is the new writer safe?");
    await expect(strip.getByText("Asked: the answer comes in this item's thread.")).toHaveCount(0);
    await page.unroute(`**/api/reviews/${rid}/comments`);                               // the server answers this time
    await strip.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(strip.getByText("Asked: the answer comes in this item's thread.")).toBeVisible();   // landed: the box is shut
    await expect(box).toHaveCount(0);
    await expect(strip.getByRole("alert"), "the error went with the next try").toHaveCount(0);
  });

  test("a question and a comment the server refused stay with their flow: the next flow starts with fresh boxes", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    await page.goto(`${base}/s/S1?view=graph`);
    const strip = page.getByRole("region", { name: "Flow" });
    const question = strip.getByLabel("What should the AI explain?"), draft = strip.getByPlaceholder("Leave a comment…");
    // refusals with no words in them: what the page has to go on when the status line is empty too, as over HTTP/2
    await page.route(`**/api/reviews/${rid}/comments`, (route) =>
      route.request().method() === "POST" ? route.fulfill({ status: 500, json: { detail: "" } }) : route.continue());
    await explainItem(strip, "Ask a question…");
    await question.fill("is the new writer safe?");
    await strip.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(strip.getByText("The question could not be sent.")).toBeVisible();
    await strip.getByRole("button", { name: "+ comment" }).click();
    await draft.fill("flush should retry");
    await strip.getByRole("button", { name: "Comment", exact: true }).click();
    await expect(strip.getByText("The comment could not be posted.")).toBeVisible();
    await strip.getByRole("button", { name: "Next flow" }).click();
    await expect(strip.locator(".ws-flow-pos")).toHaveText("flow 2 of 2");
    await expect(strip.getByText("The question could not be sent."), "the question's failure stays with flow 1").toHaveCount(0);
    await expect(question, "…and so does the question, which would have been sent about flow 2").toHaveCount(0);
    await expect(strip.getByText("The comment could not be posted."), "…and the comment's failure").toHaveCount(0);
    await strip.getByRole("button", { name: "+ comment" }).click();
    await expect(draft, "…and the draft, which would have been posted on flow 2").toHaveValue("");
  });

  test("when the review's budget is spent, tortoise says so and the owner can raise it from the reply", async ({ page }) => {
    await startReview(page);
    const usage = await openAiUsage(page);
    await usage.getByLabel("New budget").fill("6");          // the run used 6: verdicts, summary, 1 flow, 1 finding, 2 story accounts
    await usage.getByRole("button", { name: "Raise budget" }).click();
    await expect(page.getByRole("button", { name: "AI 6/6" })).toBeVisible();          // at the limit the pill comes back
    expect(await contrast(page, ".ws-head .ai-pill")).toBeGreaterThanOrEqual(4.5);   // readable on the light head
    await usage.getByRole("button", { name: "Close" }).click();
    const { viewer, box } = await commentFromIndex(page);
    await box.fill("@tortoise does this leak?");
    await viewer.getByRole("button", { name: "Comment", exact: true }).click();
    const reply = viewer.locator(".comment.ai");
    await expect(reply).toContainText("I couldn't answer: this review has used its 6 AI calls; the owner can raise it.");
    await expect(reply.locator(".comment-body")).not.toHaveClass(/\bai-text\b/);        // the app wrote this one, not the AI
    await expect(reply.locator(".comment-body .vh")).toHaveCount(0);                      // so no "Written by AI." for a screen reader
    await reply.getByRole("button", { name: "Raise budget" }).click();
    await expect(page.getByRole("dialog", { name: "AI usage" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "AI usage" })).toHaveCount(0);
    await expect(reply.getByRole("button", { name: "Raise budget" }), "Escape hands focus back to the button that opened the panel").toBeFocused();
  });
});

test.describe("without an AI", () => {
  test("@tortoise is greyed out with the reason, and there are no AI controls", async ({ page }) => {
    await startReview(page);
    await expect(page.getByRole("button", { name: /^AI \d+/ })).toHaveCount(0);
    await expect((await reviewMenu(page)).getByRole("menuitem", { name: /^AI calls used/ })).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: /^(Explain|Summarise|Ask…)$/ })).toHaveCount(0);
    const { viewer, box } = await commentFromIndex(page);
    await box.pressSequentially("@");
    const first = viewer.getByRole("listbox", { name: "Mention" }).getByRole("option").first();
    await expect(first).toContainText("no AI is configured for CodeTortoise");
    await expect(first).toHaveAttribute("aria-disabled", "true");
    await box.press("Enter");                                             // nothing is inserted
    await expect(box).toHaveValue("@");
  });
});
