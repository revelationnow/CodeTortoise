import { devices, expect, test } from "@playwright/test";
import { expectNamed, expectNoNodeIds, startReview } from "./helpers";

/** The detail panel (spec 2026-10-04-review-workspace §3.7): a node's code or a file's diff, on demand. */

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a file from the rail opens its diff; ✕ closes it", async ({ page }) => {
    const base = await startReview(page);
    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
    await expect(page).toHaveURL(/\?open=file%3A%2F%2Ffixture%2Fdriver%2Fuart\.c$/);
    const panel = page.getByRole("complementary", { name: "Code: uart.c" });
    await expect(panel.locator(".ws-detail-path")).toHaveText("//fixture/driver/uart.c");
    await expect(panel.locator(".bd-code")).toBeVisible();
    await expect(panel.getByLabel("Changelist")).toHaveValue("all");
    await panel.getByRole("button", { name: "Full file" }).click();
    await expect(panel.locator(".bd-gap")).toHaveCount(0);
    await expectNamed(page);
    await panel.getByRole("link", { name: "Close the code" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}$`));
    await expect(page.locator(".ws-detail")).toHaveCount(0);
  });

  test("a node opens its function, its story and the full file", async ({ page }) => {
    const base = await startReview(page);
    const names = await page.evaluate(async (b) => (await fetch(`/api/reviews/${b.split("/")[2]}/names`)).json(), base);
    const send = Object.entries(names as Record<string, { label: string }>).find(([, n]) => n.label === "uart_send")![0];
    await page.goto(`${base}?open=${send}`);
    const panel = page.getByRole("complementary", { name: "Code: uart_send" });
    await expect(panel.locator(".ws-badge")).toHaveText("changed");
    await expect(panel.locator(".ws-detail-path")).toContainText("//fixture/driver/uart.c · lines");
    await expect(panel.locator(".bd-code")).toBeVisible();
    await panel.getByRole("button", { name: "Full file" }).click();
    await expect(panel.getByLabel("Changelist")).toBeVisible();
    await panel.getByRole("link", { name: /^Go to story S1/ }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1$`));
    await expectNoNodeIds(page);
  });

  test("the diff colours added lines, highlights code and fills annotations, outside any graph", async ({ page }) => {
    await startReview(page);
    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
    const file = page.getByRole("complementary", { name: "Code: uart.c" });
    const css = (sel: string, prop: string) => file.locator(sel).first().evaluate((e, p) => getComputedStyle(e).getPropertyValue(p), prop);
    const clear = "rgba(0, 0, 0, 0)";
    expect(await css(".bd-ln.a", "background-color")).not.toBe(clear);
    expect(await css(".bd-ann", "background-color")).not.toBe(clear);
    expect(await css(".hl-kw", "color")).not.toBe(await css(".bd-ln", "color"));
  });

  test("a line comment in a file's diff shows in that function's code", async ({ page }) => {
    const base = await startReview(page);
    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
    const file = page.getByRole("complementary", { name: "Code: uart.c" });
    await file.getByRole("button", { name: "Stacked" }).click();
    await file.locator(".bd-ln.a", { hasText: "return -2;" }).first().click();
    await file.getByPlaceholder("Leave a comment…").fill("Does logger_flush handle -2?");
    await file.getByRole("button", { name: "Comment", exact: true }).click();
    await expect(file.getByText("Does logger_flush handle -2?")).toBeVisible();
    const names = await page.evaluate(async (b) => (await fetch(`/api/reviews/${b.split("/")[2]}/names`)).json(), base);
    const send = Object.entries(names as Record<string, { label: string }>).find(([, n]) => n.label === "uart_send")![0];
    await page.goto(`${base}?open=${send}`);
    await expect(page.getByRole("complementary", { name: "Code: uart_send" }).getByText("Does logger_flush handle -2?")).toBeVisible();
  });

  test("one changelist's diff keeps the comments made on it", async ({ page }) => {
    await startReview(page);
    await page.locator(".ws-rail").getByRole("button", { name: /Files/ }).click();
    await page.locator(".ws-rail").getByRole("link", { name: "Open uart.c's diff" }).click();
    const file = page.getByRole("complementary", { name: "Code: uart.c" });
    await expect(file.locator(".act")).toContainText("edit");
    await file.getByRole("button", { name: "Stacked" }).click();
    await file.getByLabel("Changelist").selectOption("101");
    await file.locator(".bd-ln.a").first().click();
    await file.locator("textarea").fill("only in CL 101");
    await file.getByRole("button", { name: "Comment", exact: true }).click();
    await expect(file.getByText("only in CL 101")).toBeVisible();
    await file.getByLabel("Changelist").selectOption("all");
    await expect(file.getByText("only in CL 101")).toHaveCount(0);
    await file.getByLabel("Changelist").selectOption("101");
    await expect(file.getByText("only in CL 101")).toBeVisible();
  });

  test("a side effect on the whole change opens its file at a folded line, shown", async ({ page }) => {
    await startReview(page);
    await page.locator(".ws-rail").getByRole("link", { name: "Go to the whole change" }).click();
    await page.getByRole("link", { name: "Open uart_init at line 8" }).click();       // line 8: outside the hunks
    await expect(page.getByRole("complementary", { name: "Code: uart.c" }).locator('.focus[data-n="8"]')).toBeVisible();
  });

  test("review, layer and function comments show where they belong", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    const board = await (await page.request.get(`/api/reviews/${rid}/board`)).json();
    const send = board.nodes.find((n: { label: string }) => n.label === "uart_send");
    const post = (body: string, anchor_kind: string, anchor: object) =>
      page.request.post(`/api/reviews/${rid}/comments`, { data: { body, anchor_kind, anchor } });
    await post("overall: please split the CLs", "review", {});
    await post("driver layer looks risky", "chapter", { level: send.layer });
    await post("why -2 and not -EINVAL?", "function", { key: send.key });
    await page.goto(`${base}?open=${send.id}`);
    await expect(page.getByRole("complementary", { name: "Code: uart_send" }).getByText("why -2 and not -EINVAL?")).toBeVisible();
    const talk = page.locator("section", { has: page.getByRole("heading", { name: "Discussion" }) });
    await expect(talk.getByText("overall: please split the CLs")).toBeVisible();
    await expect(talk.getByText("driver layer looks risky")).toBeVisible();
    await talk.getByPlaceholder("Start another thread…").first().fill("agreed");
    await talk.getByRole("button", { name: "Comment" }).first().click();
    await expect(talk.getByText("agreed")).toBeVisible();
  });

  test("an unknown node says so", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}?open=N99999`);
    await expect(page.locator(".ws-detail .banner")).toContainText("This function isn't in this review.");
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("the code opens as a full-screen sheet whose top bar names it", async ({ page }) => {
    const base = await startReview(page);
    await page.goto(`${base}?open=${encodeURIComponent("file://fixture/driver/uart.c:17")}`);
    await expect(page.locator(".ws-rail, .ws-centre")).toHaveCount(0);
    const bar = page.locator(".ws-detail .ws-phonebar");
    await expect(bar).toContainText("uart.c");
    await bar.getByRole("link", { name: "Close the code" }).click();
    await expect(page.locator(".ws-detail")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});

test.describe("neighbours", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("callers and callees; a row moves the panel and Back returns", async ({ page }) => {
    const base = await startReview(page);
    const names = await page.evaluate(async (b) => (await fetch(`/api/reviews/${b.split("/")[2]}/names`)).json(), base);
    const send = Object.entries(names as Record<string, { label: string }>).find(([, n]) => n.label === "uart_send")![0];
    await page.goto(`${base}?open=${send}`);
    await page.getByRole("tab", { name: "Neighbours" }).click();
    await expect(page).toHaveURL(new RegExp(`open=${send}&tab=neighbours$`));
    const callers = page.getByRole("region", { name: "Callers" });
    await expect(callers.getByRole("link", { name: "Open logger_flush's neighbours" })).toBeVisible();
    await expect(page.getByRole("region", { name: "This function" })).toContainText("uart_send");
    await callers.getByRole("link", { name: "Open logger_flush's neighbours" }).click();
    await expect(page.getByRole("region", { name: "This function" })).toContainText("logger_flush");
    await expect(page.getByRole("region", { name: "Callees" })).toContainText("uart_send");
    await page.goBack();
    await expect(page.getByRole("region", { name: "This function" })).toContainText("uart_send");
    await page.getByRole("tab", { name: "Diff" }).click();
    await expect(page.locator(".ws-detail .bd-code")).toBeVisible();
    await expectNoNodeIds(page);
    await expectNamed(page);
  });
});

test.describe("neighbours off every board", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a row for a function outside the name index still names it, shows its code and keeps walking", async ({ page }) => {
    const base = await startReview(page);
    const rid = base.split("/")[2];
    const names = await (await page.request.get(`/api/reviews/${rid}/names`)).json() as Record<string, { label: string }>;
    let from = "", to = "";
    for (const nid of Object.keys(names)) {
      const nb = await (await page.request.get(`/api/reviews/${rid}/nodes/${nid}/neighbours?limit=999`)).json();
      const off = [...nb.callers.items, ...nb.callees.items].find((i: { id: string; label: string }) => i.label === "logger_init" && !(i.id in names));
      if (off) { from = nid; to = off.id; break; }
    }
    expect(to).not.toBe("");
    await page.goto(`${base}?open=${from}&tab=neighbours`);
    await page.getByRole("link", { name: "Open logger_init's neighbours" }).click();
    await expect(page).toHaveURL(new RegExp(`open=${to}&tab=neighbours$`));
    const panel = page.getByRole("complementary", { name: "Code: logger_init" });
    await expect(panel.getByRole("region", { name: "This function" })).toContainText("logger_init");
    await expect(panel.getByRole("tab", { name: "Neighbours" })).toBeVisible();
    await panel.getByRole("tab", { name: "Diff" }).click();
    await expect(panel.locator(".ws-detail-path")).toContainText("logger.c · line");
    await expect(panel.locator(".bd-code")).toBeVisible();
    await expect(panel.locator(".banner")).toHaveCount(0);
  });
});

test.describe("a split review", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });
  type Node = { id: string; label: string; path: string | null; range: number[] | null; change: unknown; fields?: { id: string }[] };

  test("a field without a story shows its struct from the story being read; a context function its slice on its part", async ({ page }) => {
    const base = await startReview(page, "201 202");
    const rid = base.split("/")[2];
    const get = async (url: string) => (await page.request.get(`/api/reviews/${rid}/${url}`)).json();
    const names = await get("names") as Record<string, { story: string | null; path: string | null }>;
    let field: [string, string] | null = null;
    for (const st of (await get("stories")).stories as { id: string }[]) {
      const f = ((await get(`stories/${st.id}`)).graph?.nodes as Node[] ?? []).flatMap((n) => n.fields ?? [])
        .find((x) => names[x.id] && !names[x.id].story && !names[x.id].path);
      if (f) { field = [st.id, f.id]; break; }
    }
    expect(field).not.toBeNull();
    await page.goto(`${base}/s/${field![0]}?open=${field![1]}`);
    const panel = page.locator(".ws-detail");
    await expect(panel.locator(".ws-badge")).toHaveText("field");
    await expect(panel.locator(".bd-code")).toBeVisible();
    await expect(panel.getByText(/No code to show/)).toHaveCount(0);

    let fn: [string, Node] | null = null;
    for (const c of (await get("overview")).clusters as { id: string }[]) {
      const n = ((await get(`board?cluster=${c.id}`)).nodes as Node[])
        .find((x) => !x.change && x.range && names[x.id] && !names[x.id].story);
      if (n) { fn = [c.id, n]; break; }
    }
    expect(fn).not.toBeNull();
    await page.goto(`${base}/c/${fn![0]}?open=${fn![1].id}`);
    await expect(panel.locator(".ws-detail-path")).toContainText(`lines ${fn![1].range![0]}–${fn![1].range![1]}`);
    await expect(panel.getByRole("button", { name: "Function" })).toHaveAttribute("aria-pressed", "true");
  });
});
