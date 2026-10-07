import { expect, type Page, test } from "@playwright/test";
import { startReview } from "./helpers";

/** The map and the stories, related: each changed node on a map is tagged with its story; a story in the rail lights its
 * nodes on the map; a story's "Show on the map" opens its map with the story lit and in view. */

type StorySet = { stories: { id: string; board: string | null }[]; node_story: Record<string, string> };
const storiesOf = async (page: Page, rid: string) => (await page.request.get(`/api/reviews/${rid}/stories`)).json() as Promise<StorySet>;
const ids = (page: Page, cls: string) => page.locator(`.bd-canvas .bd-node.${cls}`).evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.id!).sort());

test.describe("one board", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a map's nodes carry their story, and a story in the rail lights its own", async ({ page }) => {
    const base = await startReview(page), rid = base.split("/")[2];
    const ss = await storiesOf(page, rid);
    await page.goto(`${base}?view=graph`);
    await page.getByRole("button", { name: "Whole graph" }).click();
    const canvas = page.locator(".bd-canvas");
    await expect(canvas.locator(".bd-node").first()).toBeVisible();
    const drawn = await canvas.locator(".bd-node").evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.id!));
    const s1 = drawn.filter((n) => ss.node_story[n] === "S1").sort();
    expect(s1.length).toBeGreaterThan(0);
    const changed = await canvas.locator(".bd-node.chg").evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.id!));
    expect(changed.filter((x) => ss.node_story[x]).length).toBeGreaterThan(0);
    for (const n of changed.filter((x) => ss.node_story[x]))                     // changed code carries its story's tag
      await expect(canvas.locator(`.bd-node[data-id="${n}"] .bd-story`)).toHaveText(ss.node_story[n]);
    await expect(canvas.locator(".bd-node:not(.chg) .bd-story")).toHaveCount(0);

    await page.locator(".ws-rail").getByRole("link", { name: /^Go to story S1/ }).hover();
    await expect.poll(() => ids(page, "instory")).toEqual(s1);
    expect((await ids(page, "offstory")).length).toBe(drawn.length - s1.length);
    await page.locator(".ws-head h1").hover();                         // off the rail
    await expect.poll(() => ids(page, "offstory")).toEqual([]);

    const tagged = s1.find((n) => changed.includes(n))!;
    await canvas.locator(`.bd-node[data-id="${tagged}"]`).getByRole("button", { name: "Go to story S1" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1`));
  });

  test("a story's Show on the map opens the whole graph with it lit, until cleared", async ({ page }) => {
    const base = await startReview(page), rid = base.split("/")[2];
    const ss = await storiesOf(page, rid);
    await page.goto(`${base}/s/S1`);
    await page.getByRole("link", { name: "Show S1 on the map" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}\\?view=graph&story=S1$`));
    const drawn = await page.locator(".bd-canvas .bd-node").evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.id!));
    await expect.poll(() => ids(page, "instory")).toEqual(drawn.filter((n) => ss.node_story[n] === "S1").sort());
    const chip = page.locator(".bd-toolbar .bd-hl");
    await expect(chip).toContainText("S1");
    await chip.getByRole("button", { name: "Stop showing S1" }).click();
    await expect(page).toHaveURL(new RegExp(`${base}\\?view=graph$`));
    await expect.poll(() => ids(page, "offstory")).toEqual([]);
    await page.goBack();                                                 // the chip replaced the entry: Back is the story
    await expect(page).toHaveURL(new RegExp(`${base}/s/S1`));
  });
});

test.describe("a split review", () => {
  test.use({ baseURL: "http://127.0.0.1:8796", viewport: { width: 1440, height: 900 } });

  test("Show on the map opens the story's own part", async ({ page }) => {
    const base = await startReview(page, "201 202"), rid = base.split("/")[2];
    const st = (await storiesOf(page, rid)).stories.find((s) => s.board)!;
    await page.goto(`${base}/s/${st.id}?view=graph`);
    await page.getByRole("link", { name: `Show ${st.id} on the map` }).click();
    await expect(page).toHaveURL(new RegExp(`${base}/c/${st.board}\\?story=${st.id}$`));
    await expect.poll(async () => (await ids(page, "instory")).length).toBeGreaterThan(0);
  });
});
