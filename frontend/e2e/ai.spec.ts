import { expect, type Locator, type Page, test } from "@playwright/test";
import { explainItem, login, openAiUsage, openIndex, startReview, storyLink } from "./helpers";

const AI = "http://127.0.0.1:8798";      // e2e/serve-ai.sh: CodeTortoise with the fake model in e2e/fake_llm.py

/** An open menu ends on the screen, and the page or panel around it has nothing running past its right edge (a page that
 * scrolls would scroll sideways, one that clips would cut the menu off) and has not been scrolled sideways. */
async function menuFits(page: Page, menu: Locator) {
  await expect(menu).toBeVisible();
  const box = (await menu.boundingBox())!;
  expect(box.x, "the menu starts on the screen").toBeGreaterThanOrEqual(0);
  expect(box.x + box.width, "the menu ends on the screen").toBeLessThanOrEqual(page.viewportSize()!.width);
  const around = await menu.evaluate((el) => {
    const holder = el.closest(".ws-page, .ws-detail-body")!;
    return { name: holder.className, over: holder.scrollWidth - holder.clientWidth, left: holder.scrollLeft };
  });
  expect(around.over, `nothing in ${around.name} runs past its right edge`).toBeLessThanOrEqual(0);
  expect(around.left, `${around.name} is not scrolled sideways`).toBe(0);
}

/** No Explain control sits inside AI-written text: its button, menu, Ask box and errors are not the AI's words, so the
 * edge, the hover and "Written by AI." must not cover them. A control has to be on the page, so the zeros mean something. */
async function explainOutsideAiText(page: Page) {
  await expect(page.locator(".ai-ask").first()).toBeVisible();
  await expect(page.locator(".ai-text button")).toHaveCount(0);
  await expect(page.locator(".ai-text .ai-ask")).toHaveCount(0);
}

test.describe("with an AI", () => {
  test.use({ baseURL: AI });

  test("Explain rewrites a flow that the up-front pass left", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}?view=graph&flow=2`);
    const text = page.getByRole("region", { name: "Flow" }).locator(".ws-flow-text");
    const what = text.locator("p").first();                                  // the flow's paragraph; its Explain menu follows it
    const button = text.getByRole("button", { name: "Explain", exact: true });
    await expect(button).toHaveAttribute("aria-haspopup", "menu");
    await button.click();
    const item = text.getByRole("menuitem", { name: "Explain", exact: true });
    await expect(item).toHaveAttribute("title", /^1 AI call · \d+ left on this review$/);
    await expect(what).not.toContainText("reaches logger_flush, which drops it");
    await item.click();
    await expect(what).toContainText("The new -2 from uart_send reaches logger_flush, which drops it.", { timeout: 30_000 });
    await expect(what).toHaveClass(/\bai-text\b/);
    await expect(what).toHaveAttribute("title", "Written by AI");
    await button.click();
    await expect(text.getByRole("menuitem", { name: "Explain again" })).toBeVisible();
    await explainOutsideAiText(page);                                        // the AI's paragraph, and the menu beside it
    await page.keyboard.press("Escape");                                     // Escape closes it and returns to the button
    await expect(text.getByRole("menu")).toHaveCount(0);
    await expect(button).toBeFocused();
  });

  test("Explain retells a story's title and summary, on the story and in the rail", async ({ page }) => {
    await startReview(page);
    await (await storyLink(page, /^Go to story S1/)).click();
    const head = page.locator(".ws-story-head");
    await expect(head.locator("h2 .ai-name")).toHaveCount(0);                // this server's up-front pass skips stories
    await explainItem(head, "Explain");
    await expect(head.locator("h2")).toContainText("uart_send's new error count reaches uart_errors", { timeout: 30_000 });
    await expect(head.locator("h2 .ai-name")).toHaveAttribute("title", "Written by AI");   // the title…
    await expect(head.locator(".st-summary .ai-text").first()).toBeVisible();              // …and the summary, retold
    await head.getByRole("button", { name: "Explain", exact: true }).click();
    await expect(head.getByRole("menuitem", { name: "Explain again" })).toBeVisible();
    await explainOutsideAiText(page);                                                       // the summary's edge stops short of Explain
    await page.keyboard.press("Escape");
    await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }))
      .toContainText("uart_send's new error count reaches uart_errors");
  });

  test("Explain on a story with its graph open neither flashes Loading nor redraws the graph", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}/s/S1?view=graph`);
    await expect(page.locator(".ws-graph .bd-node").first()).toBeVisible();
    await page.getByRole("button", { name: "Whole graph" }).click();
    await page.evaluate(() => {
      const w = window as unknown as { loading: number };
      w.loading = 0;
      (document.querySelector(".ws-graph") as HTMLElement).dataset.kept = "yes";     // gone if the graph remounts
      new MutationObserver(() => { if (document.querySelector("main")?.textContent?.includes("Loading S")) w.loading++; })
        .observe(document.body, { subtree: true, childList: true, characterData: true });
    });
    const head = page.locator(".ws-story-head");
    await explainItem(head, "Explain");
    await expect(head.locator("h2")).toContainText("uart_send's new error count reaches uart_errors", { timeout: 30_000 });
    await expect(page.locator(".ws-graph .bd-node").first()).toBeVisible();
    expect(await page.evaluate(() => (window as unknown as { loading: number }).loading)).toBe(0);
    await expect(page.locator(".ws-graph")).toHaveAttribute("data-kept", "yes");
    await expect(page.getByRole("button", { name: "Whole graph" })).toHaveAttribute("aria-pressed", "true");
  });

  test("a story shows the flow narrative the up-front pass wrote, and Explain on another flow updates it", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    const board = await (await page.request.get(`/api/reviews/${rid}/board`)).json();
    const ss = await (await page.request.get(`/api/reviews/${rid}/stories`)).json();
    const told = board.flows.find((f: { what_source: string }) => f.what_source === "llm");
    const sid = ss.flow_story[told.id];
    const s = ss.stories.find((x: { id: string }) => x.id === sid);
    await page.goto(`${base}/s/${sid}?view=graph&flow=${s.flows.indexOf(told.id) + 1}`);
    const text = page.getByRole("region", { name: "Flow" }).locator(".ws-flow-text");
    const what = text.locator("p").first();                                    // the flow's paragraph; its Explain menu follows it
    await expect(what).toHaveClass(/\bai-text\b/);                             // the board's narrative, on the story
    await text.getByRole("button", { name: "Explain", exact: true }).click();
    await expect(text.getByRole("menuitem", { name: "Explain again" })).toBeVisible();
    await explainOutsideAiText(page);                                          // the edge and the hover are the narrative's alone
    const other = ss.stories.flatMap((x: { id: string; flows: string[] }) => x.flows.map((f) => [x.id, f]))
      .find(([, f]: string[]) => f !== told.id)!;
    const st = ss.stories.find((x: { id: string }) => x.id === other[0]);
    await page.goto(`${base}/s/${other[0]}?view=graph&flow=${st.flows.indexOf(other[1]) + 1}`);
    await explainItem(text, "Explain");
    await expect(what).toContainText("The new -2 from uart_send reaches logger_flush, which drops it.", { timeout: 30_000 });
    await text.getByRole("button", { name: "Explain", exact: true }).click();
    await expect(text.getByRole("menuitem", { name: "Explain again" })).toBeVisible();
  });

  test("a high finding's page shows the analysis the up-front pass wrote, without asking", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    const findings: { id: string; severity: string }[] = await (await page.request.get(`/api/reviews/${rid}/findings`)).json();
    const high = findings.find((f) => f.severity === "high")!;
    expect(high, "the fixture has a high finding").toBeTruthy();
    await page.goto(`${base}/f/${high.id}?details=1`);
    const ai = page.getByRole("region", { name: "Analysis", exact: true });
    await expect(ai).toContainText("uart_send can now return -2, and logger_flush drops it.", { timeout: 30_000 });
    await expect(ai.locator(".ai-text")).toHaveAttribute("title", "Written by AI");
    await expect(page.locator(".ai-label")).toHaveCount(0);
    await ai.getByRole("button", { name: "Explain", exact: true }).click();
    await expect(ai.getByRole("menuitem", { name: "Explain again" })).toBeVisible();
    await explainOutsideAiText(page);                                            // Explain sits after the analysis, not in it
  });

  test("a hypothesis the AI proposes is AI text, with its hover", async ({ page }) => {
    const base = await startReview(page);
    const findings = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/findings`)).json() as { id: string; title: string }[];
    const errors = findings.find((f) => f.title.startsWith("uart_send now writes Uart::errors"))!;   // the one finding the fake model proposes one for
    await page.goto(`${base}/f/${errors.id}?details=1`);
    const hypotheses = page.getByRole("region", { name: "Possible side effects", exact: true });
    await expect(hypotheses.locator("li")).toHaveCount(1, { timeout: 30_000 });           // written up front, with the analysis
    const one = hypotheses.locator("li.ai-text");
    await expect(one).toHaveCount(1);
    await expect(one).toHaveAttribute("title", "Written by AI");
    await expect(one).toContainText("Another reader of Uart::errors may see the count change between two reads.");
    await expect(one.locator(".vh")).toHaveText("Written by AI. ");
  });

  test("Ask a question… opens a box that Escape or a second pick closes, back on the Explain button; the box is not AI text", async ({ page }) => {
    const base = await startReview(page);
    const findings: { id: string; severity: string }[] = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/findings`)).json();
    await page.goto(`${base}/f/${findings.find((f) => f.severity === "high")!.id}?details=1`);
    const ai = page.getByRole("region", { name: "Analysis", exact: true });
    await expect(ai.locator(".ai-text")).toHaveAttribute("title", "Written by AI", { timeout: 30_000 });   // the analysis is the AI's; Explain follows it
    const button = ai.getByRole("button", { name: "Explain", exact: true });
    const box = ai.getByRole("textbox", { name: "What should the AI explain?" });
    await explainItem(ai, "Ask a question…");
    await expect(box).toBeFocused();
    await explainOutsideAiText(page);                                            // the Ask box and its button are no part of the AI's text
    const hover = await box.evaluate((el) => el.closest("[title]")?.getAttribute("title") ?? "");
    expect(hover, "the box, its note and its errors are not the AI's text").not.toMatch(/^Written by AI/);
    await page.keyboard.press("Escape");
    await expect(box).toHaveCount(0);
    await expect(button).toBeFocused();
    await explainItem(ai, "Ask a question…");                                        // the item opens the box…
    await expect(box).toBeFocused();
    await explainItem(ai, "Ask a question…");                                        // …and shuts it again
    await expect(box).toHaveCount(0);
    await expect(button).toBeFocused();
  });

  test("a side effect the AI judges a hazard turns red and says why; one it clears stays neutral with its reason", async ({ page }) => {
    const base = await startReview(page);
    const findings = await (await page.request.get(`/api/reviews/${base.split("/")[2]}/findings`)).json() as { id: string; title: string }[];
    const errors = findings.find((f) => f.title.startsWith("uart_send now writes Uart::errors"))!;
    const tx = findings.find((f) => f.title.startsWith("uart_send now writes Stats::tx"))!;
    await page.goto(`${base}/f/${errors.id}?details=1`);
    await expect(page.locator(".ws-finding h2 .badge")).toHaveText("high");
    await expect(page.locator(".ws-verdict")).toContainText("Hazard — uart_errors assumes only uart_init writes Uart::errors.");
    await expect(page.locator(".ws-verdict")).toHaveClass(/\bai-text\b/);
    await page.goto(`${base}/f/${tx.id}?details=1`);
    await expect(page.locator(".ws-finding h2 .badge")).toHaveText("info");
    await expect(page.locator(".ws-verdict")).toContainText("No clear hazard — Nothing else depends on the value it writes.");
    await page.goto(`${base}/s/S1?view=graph`);                              // a story's flows are on its graph
    const lands = page.getByRole("region", { name: "Flow" }).locator(".ws-flow-lands");
    await expect(lands).toContainText("⚠ Side effect lands on uart_errors.");
    await expect(lands.locator(".ws-flow-why")).toHaveText("Written by AI. uart_errors assumes only uart_init writes Uart::errors.");
    await expect(lands.locator(".ws-flow-why")).toHaveClass(/\bai-text\b/);
    await expect(lands.locator(".ws-flow-why")).toHaveCSS("display", "block");        // a reason that wraps keeps its edge on every line
    await expect(lands).not.toContainText("AI:");
  });

  test("Summarise sums up a file in its diff", async ({ page }) => {
    await startReview(page);
    await openIndex(page, "Files");
    await page.getByRole("link", { name: "Open uart.c's diff" }).click();
    const panel = page.getByRole("complementary", { name: "Code: uart.c" });
    await explainItem(panel, "Summarise");
    await expect(panel).toContainText("This file now counts transmit errors.", { timeout: 30_000 });
    await expect(panel).toContainText("Check the readers of uart_errors.");
    const summary = panel.locator(".ai-summary");
    await expect(summary).toHaveClass(/\bai-text\b/);
    await expect(summary).toHaveAttribute("title", /^Written by AI · \S+/);
    await expect(summary.locator("h4")).toHaveText("Summary");
    await explainOutsideAiText(page);                                                // Summarise ▾ is not inside the summary's edge
  });

  test("the Summarise menu in the code panel stays on the screen when its button ends the toolbar's row", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}?open=${encodeURIComponent("file://fixture/driver/uart.c")}`);
    const panel = page.getByRole("complementary", { name: "Code: uart.c" });
    await panel.getByRole("button", { name: "Summarise", exact: true }).click();
    await menuFits(page, panel.getByRole("menu"));
  });

  test.describe("on a phone", () => {
    test.use({ viewport: { width: 390, height: 844 } });

    // An Explain button follows its paragraph and may sit at a phone's right edge. Right-aligning what holds the paragraph and
    // the button puts the button there whatever the fixture's text says; a menu opening rightwards from it would run past
    // the screen: a page that scrolls would scroll sideways, a page that clips would cut the menu's items off.
    const atTheEdge: [string, string, (page: Page) => Locator][] = [
      ["a finding's analysis, on a page that scrolls", "/f/F1?details=1",
        (page) => page.getByRole("region", { name: "Analysis", exact: true }).locator("p.ai-text").first()],
      ["a flow's text, on a graph page that clips", "?view=graph&flow=2",
        (page) => page.getByRole("region", { name: "Flow" }).locator(".ws-flow-text p").first()],
    ];
    for (const [where, path, text] of atTheEdge) {
      test(`an Explain menu that would run past its container opens to the left: ${where}`, async ({ page }) => {
        const base = await startReview(page);
        await page.goto(`${base}${path}`);
        const holder = text(page).locator("..");                                 // the paragraph and the Explain button after it
        await holder.evaluate((el) => { el.style.textAlign = "right"; });
        await holder.getByRole("button", { name: "Explain", exact: true }).click();
        await menuFits(page, holder.getByRole("menu"));
      });
    }
  });

  test("the owner raises the budget from the review menu; a reviewer sees the usage without the control", async ({ page, browser }) => {
    await startReview(page);
    await expect(page.getByRole("button", { name: /^AI \d+\/200$/ })).toHaveCount(0);   // far from the limit: no pill
    const usage = await openAiUsage(page);
    await expect(usage).toContainText("By purpose: story_account 2 · finding 1 · flow 1 · summary 1 · verdict 1");
    await usage.getByText(/^All calls/).click();                          // the call list loads when opened
    await expect(usage.locator(".ai-calls tbody tr")).toHaveCount(6);                // + an account per behaviour story
    await usage.getByLabel("New budget").fill("300");
    await usage.getByRole("button", { name: "Raise budget" }).click();
    await expect(usage).toContainText(/This review: \d+ of 300\./);
    await expect(usage.getByLabel("Rounds per @tortoise answer")).toHaveValue("10");
    await usage.getByLabel("Rounds per @tortoise answer").fill("4");
    await usage.getByRole("button", { name: "Set rounds" }).click();
    await expect(usage).toContainText("One @tortoise answer is 1 AI call of up to 4 rounds.");

    const bob = await browser.newPage({ baseURL: AI });
    await login(bob, "bob");
    await bob.goto(page.url());
    const theirs = await openAiUsage(bob);
    await expect(theirs).toContainText("You today: 0 of 100");
    await expect(theirs.getByRole("button", { name: "Raise budget" })).toHaveCount(0);
    await expect(theirs).toContainText("One @tortoise answer is 1 AI call of up to 4 rounds.");
    await expect(theirs.getByRole("button", { name: "Set rounds" })).toHaveCount(0);
    await bob.close();
  });

  test("Health shows the AI limits and today's calls", async ({ page }) => {
    await login(page);
    await page.goto("/health");
    const card = page.locator(".card", { has: page.getByRole("heading", { name: "AI calls" }) });
    await expect(card).toContainText("Limits: 200 a review · 100 a person a day · 10 rounds for one @tortoise answer (1 call");
    await expect(card).toContainText(/Today: \d+ calls across reviews/);
  });

  test("a story tells the weak model's account: purpose, its flows and what it means, each with the AI edge", async ({ page }) => {
    await startReview(page);
    await (await storyLink(page, /^Go to story S1/)).click();
    const purpose = page.locator(".st-summary");
    await expect(purpose.locator(".ai-text")).toBeVisible({ timeout: 30_000 });
    await expect(purpose.locator(".ai-text")).toHaveAttribute("title", "Written by AI");
    await expect(purpose).toContainText("This story makes uart_send count its transmit errors.");
    const rows = page.locator(".fl-row");
    expect(await rows.count()).toBeGreaterThan(0);
    await rows.first().locator(".fl-toggle").click();                                // a row opens in place
    const card = page.getByRole("region", { name: /^Flow \d+: / });
    await expect(card.locator("> p.ai-text")).toContainText("The caller reaches uart_send on this path.");
    await expect(card.locator("> p.ai-text")).toHaveAttribute("title", "Written by AI");
    const effects = page.getByRole("region", { name: "What it means for the rest" });
    await expect(effects.locator(".ai-text")).toBeVisible();
    await expect(effects).toContainText("Code that reads Uart::errors now sees transmit errors too.");
    await expect(page.locator(".ai-label")).toHaveCount(0);
  });
});
