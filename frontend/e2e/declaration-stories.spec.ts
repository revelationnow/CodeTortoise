import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

/** A story made only of declarations (a changed header no changed function defines or calls) shows them under Before → after
 * and Where instead of two empty sections. The server's story S1 is rewritten into such a story, with the rows and files the
 * back end builds for one header edited in CL 101: by line, an added macro (its new text only), a changed type (both texts, the
 * part of the new one that differs marked), and a macro that replaced a prototype of the same name (that one's old text only). */
test("a declarations-only story lists its declarations under Before → after and Where", async ({ page }) => {
  const row = (text: string, before: string, after: string, mark: number[], added: string[] = [], removed: string[] = []) =>
    ({ kind: "declaration", text, node: null, before, after, mark, added, removed, nodes: [] });
  await page.route("**/api/reviews/*/stories/S1", async (route) => {
    let res: import("@playwright/test").APIResponse, j: any;
    try { res = await route.fetch(); j = await res.json(); }
    catch { return; }                          // the page or the test went away while it was in flight: nobody reads it
    j.reading.contracts = [
      row("`LIMIT` macro added", "", "#define LIMIT 8", []),
      row("`Widget` now has `c`; no longer has `b`", "struct Widget { int a; int b; }", "struct Widget { int a; int c; }",
          [27, 28], ["c"], ["b"]),                                     // [27, 28): the back end's differ marks the `c`
      row("`alpha` macro added", "", "#define alpha(v) beta(v)", []),
      row("`alpha` declaration removed", "int alpha(int v);", "", []),
    ];
    j.reading.where = [{ path: "inc/w.h", depot: "//fixture/inc/w.h", functions: [], cls: [101],
                         decls: [{ name: "LIMIT", line: 1 }, { name: "Widget", line: 3 }, { name: "alpha", line: 4 },
                                 { name: "alpha", line: 5 }] }];
    j.reading.cl_order = [101];
    await route.fulfill({ response: res, json: j });
  });
  const base = await startReview(page);
  await page.goto(`${base}/s/S1?sec=contracts`);
  const contracts = page.getByRole("region", { name: "Before → after" });
  await expect(contracts).toContainText("Widget now has c; no longer has b");
  const changed = contracts.locator("li", { hasText: "Widget now has" });
  await expect(changed.locator(".del")).toHaveText("struct Widget { int a; int b; }");
  await expect(changed.locator(".add")).toHaveText("struct Widget { int a; int c; }");
  await expect(changed.locator("mark")).toHaveText("c");
  const added = contracts.locator("li", { hasText: "LIMIT macro added" });       // a new macro: its text, drawn as a new side
  await expect(added.locator(".add")).toHaveText("#define LIMIT 8");
  await expect(added.locator(".del")).toHaveCount(0);
  const removed = contracts.locator("li", { hasText: "declaration removed" });   // a gone prototype: its text, drawn as an old side
  await expect(removed.locator(".del")).toHaveText("int alpha(int v);");
  await expect(removed.locator(".add")).toHaveCount(0);
  await page.goto(`${base}/s/S1?sec=where`);
  for (const name of ["Open LIMIT in inc/w.h at line 1", "Open Widget in inc/w.h at line 3", "Open alpha in inc/w.h at line 4",
                      "Open alpha in inc/w.h at line 5"]) {                  // alpha twice: a macro and a prototype share the name
    await expect(page.getByRole("link", { name })).toBeVisible();
  }
});
