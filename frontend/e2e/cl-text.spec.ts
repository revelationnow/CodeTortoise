import { expect, test } from "@playwright/test";
import { startReview } from "./helpers";

/** CL descriptions as Perforce authors write them (owner feedback 2026-10-10): HTML spans and blocks mixed with
 * Markdown, indented bullets; the heading and the rail show the first line as text, without tags. */

test.use({ viewport: { width: 1440, height: 900 } });

const DESC = '<span style="color: red">[DRV]</span> Fix uart &amp; spi\n\nChanges:\n    * reset the **FIFO**\n    * count errors\n'
  + 'Tested on rev B\n\n<div>\nInside a *div*\n</div>\n<script>window.__x = 1</script><img src="http://example.invalid/t.png" alt="logo">';

test("a CL description with HTML and indented bullets reads as written, its first line as text", async ({ page }) => {
  const base = await startReview(page);
  await page.route(/\/api\/reviews\/\d+$/, async (route) => {
    const res = await route.fetch();
    const j = await res.json();
    for (const c of j.cls) if (c.cl === 101) c.description = DESC;
    await route.fulfill({ response: res, json: j });
  });
  await page.goto(`${base}/cl/101`);
  await expect(page.locator(".ws-story-title h2")).toHaveText("CL 101 · [DRV] Fix uart & spi");
  const desc = page.locator(".ws-desc");
  await expect(desc.locator("li")).toHaveText(["reset the FIFO", "count errors"]);
  await expect(desc.locator("li strong")).toHaveText("FIFO");
  await expect(desc.locator("div em")).toHaveText("div");
  await expect(desc).toContainText("Tested on rev B");
  await expect(desc).toContainText("logo");
  await expect(desc.locator("img, script")).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __x?: number }).__x)).toBeUndefined();
  await page.goto(`${base}/i/cls`);                                           // the Index lists each CL by its first line
  const list = page.getByRole("region", { name: "Centre" });
  await expect(list).toContainText("[DRV] Fix uart & spi");
  await expect(list).not.toContainText("<span");
});
