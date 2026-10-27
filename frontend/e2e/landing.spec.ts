import { devices, expect, test } from "@playwright/test";
import { login, railReady, startReview } from "./helpers";

test.describe("desktop", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("landing page: start a review, search and filter reviews", async ({ page }) => {
    // the e2e server is shared by the whole run, so other tests' reviews are in the list too
    // its unique part is letters only: digits from the clock (…101…) would match the CL search below
    const title = `flags field only ${String(Date.now()).replace(/\d/g, (d) => "abcdefghij"[Number(d)])}`;
    await startReview(page);
    await page.goto("/");
    await page.getByLabel("Changelists (shelved or submitted)").fill("102");
    await page.getByLabel("Title (optional)").fill(title);
    await page.getByRole("button", { name: "Start review" }).click();
    await railReady(page);                                                   // a review opens on its workspace
    await page.getByRole("link", { name: "Reviews" }).first().click();

    const rows = page.locator(".rv-list .rv-row");
    await expect(rows.first()).toBeVisible();
    const total = await rows.count();
    const search = page.getByRole("searchbox", { name: "Search reviews" });
    await search.fill(title.split(" ").at(-1)!);                                       // the unique part of the title
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText(title);
    await expect(page.getByText(`1 of ${total} reviews`)).toBeVisible();
    await search.fill("flags field");
    await expect(rows.first().locator("mark").first()).toHaveText(/flags/i);
    await search.press("Escape");
    await expect(rows).toHaveCount(total);
    await search.fill("101");                                                         // a CL number
    // wait for the filter itself: no row may remain without CL 101 (reading rows.all() first raced the re-render)
    await expect(rows.filter({ hasNot: page.locator(".cl", { hasText: "101" }) })).toHaveCount(0);
    await expect(rows.first()).toBeVisible();
    await search.fill("");
    const high = page.getByRole("button", { name: /^High risk/ });
    const n = Number((await high.locator("span").textContent())!.trim());
    await high.click();
    await expect(rows).toHaveCount(n);
    // each row says what to act on; without the strong model that is the rules' top severity (review reading §5.4)
    for (const r of await rows.all()) {
      await expect(r.locator(".rv-headline")).toHaveText(/ risk$/);
      await expect(r.locator(".rv-headline")).toHaveAttribute("title", "Judged by the detectors' rules, without the strong model");
    }
    await page.getByRole("button", { name: /^Mine/ }).click();
    await expect(rows).toHaveCount(total);                                            // every review here was started by demo
  });

  test("the logo is in the top bar and the tab; /new goes to the landing page", async ({ page }) => {
    await login(page);
    await expect(page.locator(".topbar .brand svg")).toBeVisible();
    expect(await page.locator('link[rel="icon"]').getAttribute("href")).toBe("/logo.svg");
    expect((await page.request.get("/logo.svg")).headers()["content-type"]).toContain("svg");
    await page.goto("/new");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "Review a change" })).toBeVisible();
  });

  test("viewers who are not the owner see a welcome instead of the form", async ({ page }) => {
    await login(page, "bob");
    await expect(page.getByLabel("Changelists (shelved or submitted)")).toHaveCount(0);
    await expect(page.locator(".rv-hello")).toContainText("bob");
  });

  test("login is a card with the mascot", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator(".login-card svg")).toBeVisible();
    await expect(page.locator(".login-card").getByLabel("P4 user")).toBeVisible();
  });

  test("a sign-in the server refuses says why in an alert; with no words it says that it could not sign in", async ({ page }) => {
    await page.goto("/login");
    const card = page.locator(".login-card");
    await page.route("**/api/login", (route) => route.fulfill({ status: 401, json: { detail: "wrong password" } }));
    await card.getByLabel("P4 user").fill("demo");
    await card.getByRole("button", { name: "Sign in" }).click();
    await expect(card.getByText("wrong password")).toBeVisible();
    await expect(card.getByRole("alert"), "a screen reader is told of the refusal").toHaveText("wrong password");
    // a refusal with no words in it: what the page has to go on when the status line is empty too, as over HTTP/2
    await page.route("**/api/login", (route) => route.fulfill({ status: 500, json: { detail: "" } }));
    await card.getByRole("button", { name: "Sign in" }).click();
    await expect(card.getByText("You could not be signed in.")).toBeVisible();
    await expect(card.getByRole("alert")).toHaveText("You could not be signed in.");
  });

  test("a list of reviews the server will not give, and a review it will not start, are told in alerts", async ({ page }) => {
    await login(page);
    // refusals with no words in them: what the page has to go on when the status line is empty too, as over HTTP/2
    await page.route("**/api/reviews", (route) => route.fulfill({ status: 500, json: { detail: "" } }));
    await page.reload();
    await expect(page.locator(".rv-main").getByText("The reviews could not be loaded.")).toBeVisible();
    await expect(page.locator(".rv-main").getByRole("alert")).toHaveText("The reviews could not be loaded.");
    await page.getByLabel("Changelists (shelved or submitted)").fill("101");
    await page.getByRole("button", { name: "Start review" }).click();
    await expect(page.locator(".rv-hello").getByText("The review could not be started.")).toBeVisible();
    await expect(page.locator(".rv-hello").getByRole("alert")).toHaveText("The review could not be started.");
  });

  test("a start the server refuses again is told again: the old refusal goes while the new attempt waits, and an identical one comes back", async ({ page }) => {
    await login(page);
    // refusals with no words in them: what the page has to go on when the status line is empty too, as over HTTP/2
    await page.route("**/api/reviews", (route) =>
      route.request().method() === "POST" ? route.fulfill({ status: 500, json: { detail: "" } }) : route.fallback());
    const hello = page.locator(".rv-hello");
    await page.getByLabel("Changelists (shelved or submitted)").fill("101");
    await page.getByRole("button", { name: "Start review" }).click();
    await expect(hello.getByRole("alert")).toHaveText("The review could not be started.");
    let asked = () => {}, answer = () => {};                                 // the same refusal again, once the server has been asked
    const waiting = new Promise<void>((r) => { asked = r; }), gate = new Promise<void>((r) => { answer = r; });
    await page.route("**/api/reviews", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      asked();
      await gate;
      await route.fulfill({ status: 500, json: { detail: "" } });
    });
    await page.getByRole("button", { name: "Start review" }).click();
    await waiting;
    await expect(hello.getByRole("alert"), "a new attempt clears the last refusal at once").toHaveCount(0);
    answer();
    await expect(hello.getByRole("alert"), "an identical refusal is announced anew").toHaveText("The review could not be started.");
  });

  test("a Health page the server will not give says so in an alert, inside the page's main landmark", async ({ page }) => {
    await login(page);
    await page.route("**/api/health", (route) => route.fulfill({ status: 500, json: { detail: "" } }));
    await page.goto("/health");
    await expect(page.getByRole("main").getByText("The health checks could not be loaded.")).toBeVisible();
    await expect(page.getByRole("main").getByRole("alert")).toHaveText("The health checks could not be loaded.");
  });
});

test.describe("phone", () => {
  test.use({ viewport: devices["iPhone 13"].viewport, userAgent: devices["iPhone 13"].userAgent,
    deviceScaleFactor: devices["iPhone 13"].deviceScaleFactor, isMobile: true, hasTouch: true });

  test("landing fits the screen and the menu holds the links", async ({ page }) => {
    await login(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await expect(page.getByRole("link", { name: "Health" })).toBeHidden();
    await page.getByRole("button", { name: "Menu" }).click();
    await expect(page.getByRole("link", { name: "Health" })).toBeVisible();
    await page.getByRole("link", { name: "Health" }).click();
    await expect(page.getByRole("heading", { name: /Health/ })).toBeVisible();
  });
});
