import { expect, type Locator, type Page } from "@playwright/test";

export async function login(page: Page, user = "demo") {
  await page.goto("/login");
  await page.getByLabel("P4 user").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();
}

/** Log in as the demo owner, review fixture CLs 101+102 (the large fixture's are 201 202) from the landing page and
 * wait for the rail's stories; returns the review's address ("/r/12"). */
export async function startReview(page: Page, cls = "101 102"): Promise<string> {
  await login(page);
  await page.getByLabel("Changelists (shelved or submitted)").fill(cls);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.locator(".ws-rail").getByRole("link", { name: /^Go to story/ }).first()).toBeVisible({ timeout: 60_000 });
  return page.url().match(/\/r\/\d+/)![0];
}

/** No node id is ever shown (spec §8): visible text never matches N<digits>. */
export async function expectNoNodeIds(page: Page) {
  const text = await page.locator("main").innerText();
  expect(text.match(/\bN\d+\b/g) ?? []).toEqual([]);
}

/** Every link and button on the page has an accessible name (spec §8). */
export async function expectNamed(page: Page) {
  const unnamed = await page.locator("main a, main button, main [role=button]").evaluateAll((els) =>
    els.filter((e) => !(e.getAttribute("aria-label") || e.textContent?.trim() || e.getAttribute("title")))
       .map((e) => e.outerHTML.slice(0, 120)));
  expect(unnamed).toEqual([]);
}

/** The flow strip's ‹ › keep their place across flows and its row never scrolls sideways (spec §3.6, §8). */
export async function flowStripHolds(page: Page) {
  const strip = page.getByRole("region", { name: "Flow" });
  const next = strip.getByRole("button", { name: "Next flow" });
  const at = (await next.boundingBox())!.x;
  const row = strip.locator(".ws-flow-row");
  for (let i = 0; i < 3; i++) {
    expect(await row.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    await next.click();
    expect((await next.boundingBox())!.x).toBe(at);
  }
}

/** WCAG contrast ratio between an element's text colour and the first opaque background behind it. */
export async function contrast(page: Page, selector: string) {
  return page.locator(selector).first().evaluate((el) => {
    // rgb(0-255…) or, for color-mix() backgrounds, color(srgb 0-1…)
    const rgb = (c: string) => (c.match(/[\d.]+/g) ?? []).map(Number).map((v, i) => c.startsWith("color(") && i < 3 ? v * 255 : v);
    const lum = ([r, g, b]: number[]) => {
      const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    let bgEl: Element | null = el, bg = "";
    while (bgEl) {
      const c = getComputedStyle(bgEl).backgroundColor, a = rgb(c)[3];
      if (c && c !== "transparent" && (a === undefined || a > 0.9)) { bg = c; break; }
      bgEl = bgEl.parentElement;
    }
    const fg = lum(rgb(getComputedStyle(el).color)), b = lum(rgb(bg || "rgb(255,255,255)"));
    return (Math.max(fg, b) + 0.05) / (Math.min(fg, b) + 0.05);
  });
}

/** Each button is an icon with a name: no visible text, an svg, and a tooltip that says what it does. */
export async function expectIconsOnly(buttons: Locator) {
  const n = await buttons.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) {
    const b = buttons.nth(i);
    expect((await b.innerText()).trim()).toBe("");
    await expect(b.locator("svg")).toHaveCount(1);
    expect(await b.getAttribute("title")).toBe(await b.getAttribute("aria-label"));
  }
}
