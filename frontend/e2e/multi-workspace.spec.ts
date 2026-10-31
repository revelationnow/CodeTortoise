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
});
