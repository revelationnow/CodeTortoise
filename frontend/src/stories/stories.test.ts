import { describe, expect, it } from "vitest";
import type { Story, StorySet, StorySite } from "../board/types";
import { countLine, groupSites, sections, stepStory, wholeGraph } from "./stories";

const story = (id: string, kind: Story["kind"], extra: Partial<Story> = {}): Story => ({
  id, kind, title: id, summary: "", text_source: "template", risk: null, counts: {}, nodes: [], flows: [], findings: [],
  board: null, sub: null, subs: [], collapsed: false, ...extra,
});
const set = (stories: Story[]): StorySet => ({ summary: "", stories, node_story: {}, flow_story: {}, finding_story: {} });
const site = (path: string, line: number, test = false): StorySite => ({
  path, line, function: "f", node: null, before: "a", after: "b", test, effect: null, other_edits: null,
});

describe("stories", () => {
  it("splits the list into sections, collapsed behaviour stories apart", () => {
    const s = sections(set([story("S1", "behaviour"), story("S2", "behaviour", { collapsed: true }), story("S3", "other"),
                            story("S4", "mechanical"), story("S5", "tests")]));
    expect(s.behaviour.map((x) => x.id)).toEqual(["S1"]);
    expect(s.collapsed.map((x) => x.id)).toEqual(["S2"]);
    expect([s.other, s.mechanical, s.tests].map((xs) => xs.map((x) => x.id))).toEqual([["S3"], ["S4"], ["S5"]]);
  });

  it("steps between stories in list order, wrapping around", () => {
    const ss = set([story("S1", "behaviour"), story("S2", "other"), story("S3", "tests")]);
    expect(stepStory(ss, "S1", 1)).toBe("S2");
    expect(stepStory(ss, "S1", -1)).toBe("S3");
    expect(stepStory(ss, "S3", 1)).toBe("S1");
  });

  it("counts what a story holds, leaving zeros out", () => {
    expect(countLine(story("S1", "behaviour", { counts: { flows: 2, findings: 1, functions: 4, files: 0 } })))
      .toBe("2 flows · 1 finding · 4 functions");
    expect(countLine(story("S2", "mechanical", { counts: { sites: 152, files: 52, test_sites: 47 } })))
      .toBe("152 sites · 52 files · 47 in tests");
  });

  it("groups sites by directory then file in line order, and hides tests on request", () => {
    const sites = [site("//d/src/b.c", 9), site("//d/src/b.c", 3), site("//d/src/a.c", 1), site("//d/tests/t.c", 2, true)];
    const g = groupSites(sites, false);
    expect(g.map((d) => [d.dir, d.count])).toEqual([["//d/src", 3], ["//d/tests", 1]]);
    expect(g[0].files.map((f) => [f.name, f.sites.map((s) => s.line)])).toEqual([["a.c", [1]], ["b.c", [3, 9]]]);
    expect(groupSites(sites, true).map((d) => d.dir)).toEqual(["//d/src"]);
  });

  it("opens the whole graph on the board holding the story's first node", () => {
    expect(wholeGraph(3, story("S1", "behaviour", { nodes: ["N9"] }))).toBe("/r/3/board?node=N9");
    expect(wholeGraph(3, story("S1", "behaviour", { nodes: ["N9"], board: "C2" }))).toBe("/r/3/c/C2?node=N9");
    expect(wholeGraph(3, story("S1", "behaviour"), "N4")).toBe("/r/3/board?node=N4");     // a repeated edit's flows
    expect(wholeGraph(3, story("S1", "behaviour", { nodes: ["N9"] }), "N4")).toBe("/r/3/board?node=N9");
  });
});
