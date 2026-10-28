import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

/** A story made only of declarations (a changed header no changed function defines or calls) shows them under Before → after
 * and Where instead of two empty sections. The server's story S1 is rewritten into such a story. */
test("a declarations-only story lists its declarations under Before → after and Where", async ({ page }) => {
  await page.route("**/api/reviews/*/stories/S1", async (route) => {
    let res: import("@playwright/test").APIResponse, j: any;
    try { res = await route.fetch(); j = await res.json(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    j.reading.contracts = [{ kind: "declaration", text: "`Widget` now has `c`; no longer has `b`", node: null,
                             before: "struct Widget { int a; int b; }", after: "struct Widget { int a; int c; }",
                             mark: [23, 24], added: ["c"], removed: ["b"], nodes: [] }];
    j.reading.where = [{ path: "inc/w.h", depot: "//fixture/inc/w.h", functions: [], decls: [{ name: "Widget", line: 3 }],
                         cls: [101] }];
    await route.fulfill({ response: res, json: j });
  });
  const base = await startReview(page);
  await page.goto(`${base}/s/S1?sec=contracts`);
  const contracts = page.getByRole("region", { name: "Before → after" });
  await expect(contracts).toContainText("Widget now has c; no longer has b");
  await expect(contracts).toContainText("struct Widget { int a; int c; }");
  await page.goto(`${base}/s/S1?sec=where`);
  await expect(page.getByRole("link", { name: "Open Widget in inc/w.h at line 3" })).toBeVisible();
});
