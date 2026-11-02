import { test } from "./helpers";

/** The harness's own promise (helpers.ts's `test`): a stand-in for the server that is still at work as its test ends fails
 * no test. */
test("a stand-in still fetching the server's answer as its page closes fails no test", async ({ page }) => {
  await page.goto("/login");
  const closed = new Promise<void>((r) => page.once("close", () => r()));
  let entered = () => {};
  const working = new Promise<void>((r) => { entered = r; });
  await page.route("**/stand-in", async (route) => {
    entered();
    await closed;                                                // the answer is still on its way as the test ends
    await route.fulfill({ response: await route.fetch() });
  });
  await page.evaluate(() => { void fetch("/stand-in").catch(() => {}); });
  await working;
});

test("a test that closes its own page, stand-ins and all, ends without the harness failing it", async ({ page }) => {
  await page.goto("/login");
  await page.route("**/stand-in", (route) => route.fulfill({ body: "" }));
  await page.close();
});
