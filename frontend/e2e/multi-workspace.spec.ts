import { expect, test } from "@playwright/test";
import { login, MULTI, railReady } from "./helpers";

/** One server, two workspaces (spec 2026-10-31 §13): the owner adds the second copy of the fixture on the Workspaces page,
 * labelled with a second Perforce server, signs in there, reviews in both workspaces and sees both on the list; a link to
 * the review on the second server then signs in from its prompt. The tests run in order: the second uses the first's
 * review. */
test.describe.serial("one server, two workspaces", () => {
  test.use({ baseURL: MULTI });
  let deep = "";                                         // a CL page of the review in `second`

  test("an owner adds a workspace on a second server, signs in there and reviews in both; the list shows both", async ({ page }) => {
    test.setTimeout(240_000);                            // a workspace's checks, then two reviews
    await login(page);
    const [seed] = await (await page.request.get("/api/workspaces")).json();
    const root = (seed.fields.root as string).replace(/\/ws$/, "/second/ws");

    await page.getByRole("link", { name: "Workspaces" }).click();
    await page.getByRole("button", { name: "Add workspace" }).click();
    const form = page.getByRole("form", { name: "Add workspace" });
    await form.getByLabel("Name", { exact: true }).fill("second");   // first: Fill from root would name it after the folder, ws
    await form.getByLabel("Version control").selectOption("git");
    await form.getByLabel("Perforce server (P4PORT)").fill("second:1666");
    await form.getByLabel("User", { exact: true }).fill("demo");
    await form.getByLabel("Root on this host").fill(root);
    await form.getByRole("button", { name: "Fill from root" }).click();
    await expect(form.getByLabel("Compile database")).toHaveValue(`${root}/compile_commands.json`);
    await form.getByRole("button", { name: "Add", exact: true }).click();
    const saved = page.locator(".wsp-saved");
    await expect(saved).toContainText("second is ready.", { timeout: 60_000 });

    // the session has no sign-in on second:1666 yet, so the list leaves `second` out and the note offers the sign-in
    await saved.getByRole("link", { name: "Sign in to second:1666" }).click();
    await expect(page.getByLabel("Perforce server")).toHaveValue("second:1666");
    await page.getByLabel("P4 user").fill("demo");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Workspaces" })).toBeVisible();
    await expect(page.locator(".wsp-row b")).toHaveText(["second", "ws"]);

    for (const name of ["ws", "second"]) {
      await page.getByRole("link", { name: "Reviews" }).first().click();
      await page.getByLabel("Workspace", { exact: true }).selectOption({ label: name });
      await page.getByLabel("Changelists (shelved or submitted)").fill("101 102");
      await page.getByRole("button", { name: "Start review" }).click();
      await railReady(page);
      await expect(page.locator(".ws-where")).toHaveText(name);
    }
    deep = `${page.url().match(/\/r\/\d+/)![0]}/cl/102`;

    await page.getByRole("link", { name: "Reviews" }).first().click();
    const rows = page.locator(".rv-row");
    await expect(rows).toHaveCount(2);
    await expect(rows.locator(".rv-ws")).toHaveText(["second", "ws"]);                        // the newest first
    await page.getByRole("group", { name: "Filter by workspace" }).getByRole("button", { name: /^second/ }).click();
    await expect(rows).toHaveCount(1);
    await expect(rows).toContainText("second");

    await page.locator(".topbar .account summary").click();
    await expect(page.locator(".topbar .account")).toContainText("local as demo");
    await expect(page.locator(".topbar .account")).toContainText("second:1666 as demo");
  });

  test("a link to a review on the other server signs in from its prompt and opens where it pointed", async ({ page }) => {
    expect(deep, "the first test made the review").not.toBe("");
    await login(page);                                   // a new session: the picker starts on local, the first server
    await page.goto(deep);
    await expect(page.getByText("Sign in to second:1666 to open this review")).toBeVisible();
    await expect(page.getByLabel("Perforce server"), "the review names its server: no picker").toHaveCount(0);
    await page.getByLabel("P4 user").fill("demo");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: /^CL 102 · / })).toBeVisible({ timeout: 30_000 });
    expect(new URL(page.url()).pathname, "the same address, not the Reviews page").toBe(deep);
    await page.locator(".topbar .account summary").click();
    await expect(page.locator(".topbar .account")).toContainText("second:1666 as demo");
  });

  test("a link opened with no session at all asks for its review's server in place, then opens where it pointed", async ({ page }) => {
    expect(deep, "the first test made the review").not.toBe("");
    await page.goto(deep);                               // a new browser: no session (final review I2)
    await expect(page.getByText("Sign in to second:1666 to open this review")).toBeVisible();
    await expect(page.getByLabel("Perforce server"), "the review names its server: no picker").toHaveCount(0);
    await page.getByLabel("P4 user").fill("demo");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: /^CL 102 · / })).toBeVisible({ timeout: 30_000 });
    expect(new URL(page.url()).pathname, "the same address, not the Reviews page").toBe(deep);
    await page.locator(".topbar .account summary").click();
    await expect(page.locator(".topbar .account")).toContainText("second:1666 as demo");
  });

  test("the owner of the workspace in tortoise.yaml removes one saved on a server nobody signs in to", async ({ page }) => {
    test.setTimeout(120_000);                            // the add runs its checks (final review I5)
    await login(page);                                   // demo on local: the seed's owner
    const rows: { seed: boolean; fields: { root: string } }[] = await (await page.request.get("/api/workspaces")).json();
    const root = rows.find((w) => w.seed)!.fields.root.replace(/\/ws$/, "/typo");
    await page.getByRole("link", { name: "Workspaces" }).click();
    await page.getByRole("button", { name: "Add workspace" }).click();
    const form = page.getByRole("form", { name: "Add workspace" });
    await form.getByLabel("Name", { exact: true }).fill("typo");
    await form.getByLabel("Perforce server (P4PORT)").fill("tpyo:1666");
    await form.getByLabel("Client", { exact: true }).fill("typo");
    await form.getByLabel("User", { exact: true }).fill("nobody");
    await form.getByLabel("Root on this host").fill(root);
    await form.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.locator(".wsp-saved")).toContainText("typo is saved but not ready", { timeout: 60_000 });
    const row = page.locator(".wsp-row", { has: page.locator("b", { hasText: /^typo$/ }) });
    await expect(row, "listed to the seed's owner, though no one is signed in to its server").toBeVisible();
    page.once("dialog", (d) => d.accept());
    await row.getByRole("button", { name: "Remove" }).click();
    await expect(row).toHaveCount(0);
  });

  test("an owner who adds one on a server they aren't signed in to is told where its checks show", async ({ page, browser }) => {
    test.setTimeout(120_000);
    await login(page);                                   // demo on local: the seed's owner, who sees every workspace
    const rows: { seed: boolean; fields: { root: string } }[] = await (await page.request.get("/api/workspaces")).json();
    const base = rows.find((w) => w.seed)!.fields.root.replace(/\/ws$/, "");
    const mine = await page.request.post("/api/workspaces", { data: { name: "amys", vcs: "git", p4user: "amy", root: `${base}/amys` } });
    expect(mine.ok(), "amy owns a workspace on local, so she may add workspaces").toBe(true);
    const context = await browser.newContext({ baseURL: MULTI });
    const amy = await context.newPage();
    await login(amy, "amy");
    await amy.getByRole("link", { name: "Workspaces" }).click();
    await amy.getByRole("button", { name: "Add workspace" }).click();
    const form = amy.getByRole("form", { name: "Add workspace" });
    await form.getByLabel("Name", { exact: true }).fill("third");
    await form.getByLabel("Version control").selectOption("git");
    await form.getByLabel("Perforce server (P4PORT)").fill("third:1666");
    await form.getByLabel("User", { exact: true }).fill("amy");
    await form.getByLabel("Root on this host").fill(`${base}/third`);
    await form.getByRole("button", { name: "Add", exact: true }).click();
    // the list leaves out a workspace on a server she isn't signed in to, so the note can't follow its checks: it says
    // where they show, not that they are running (final review of branch minors, M2)
    const saved = amy.locator(".wsp-saved");
    await expect(saved).toContainText("third is saved; its checks run in the background.");
    await expect(saved).toContainText("Sign in to third:1666 to see them and start reviews in it.");
    await expect(saved).not.toContainText("running");
    await context.close();
    const all: { id: number; name: string }[] = await (await page.request.get("/api/workspaces")).json();
    for (const name of ["third", "amys"])
      expect((await page.request.delete(`/api/workspaces/${all.find((w) => w.name === name)!.id}`)).ok()).toBe(true);
  });

  test("a list answer asked for before a save never rolls the saved row back", async ({ page }) => {
    test.setTimeout(120_000);
    await login(page);                                   // demo on local: the seed's owner
    const rows: { seed: boolean; fields: { root: string } }[] = await (await page.request.get("/api/workspaces")).json();
    const base = rows.find((w) => w.seed)!.fields.root.replace(/\/ws$/, "");
    const late = await page.request.post("/api/workspaces", { data: { name: "late", vcs: "git", p4user: "demo", root: `${base}/late` } });
    expect(late.ok()).toBe(true);
    const id = (await late.json()).id;
    await expect.poll(async () => (await (await page.request.get("/api/workspaces")).json())
      .find((w: { id: number }) => w.id === id).reason).not.toBe("loading");
    await page.getByRole("link", { name: "Workspaces" }).click();
    const named = (name: string) => page.locator(".wsp-row", { has: page.locator("b", { hasText: new RegExp(`^${name}$`) }) });
    await expect(named("late")).toBeVisible();

    // the first list request from here on answers with the list as it was asked for, but only once the save is in
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    let held: Promise<void> | null = null;
    await page.route("**/api/workspaces", async (route) => {
      if (route.request().method() !== "GET" || held) return route.fallback();
      held = (async () => {
        const before = await route.fetch();
        await gate;
        await route.fulfill({ response: before });
      })();
      await held;
    });
    await named("ws").getByRole("button", { name: "Rebuild index" }).click();       // which loads the list again
    await expect.poll(() => held !== null).toBe(true);
    await named("late").getByRole("button", { name: "Edit" }).click();
    const form = page.getByRole("form", { name: "Edit late" });
    await form.getByLabel("Name", { exact: true }).fill("later");
    await form.getByRole("button", { name: "Save", exact: true }).click();
    await expect(named("later")).toBeVisible();
    release();
    await held;
    await page.waitForTimeout(1000);                     // the old answer has landed: it must change nothing
    await expect(named("later")).toBeVisible();
    await expect(named("late")).toHaveCount(0);
    await expect(page.locator(".wsp-saved")).toHaveText(/^later is saved/);
    expect((await page.request.delete(`/api/workspaces/${id}`)).ok()).toBe(true);
  });
});
