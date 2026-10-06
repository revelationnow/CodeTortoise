import { describe, expect, it } from "vitest";
import type { Story, StorySet, StorySite } from "../board/types";
import { citeTarget, countLine, groupSites, reasonText, relatedLabel, reviewTargets, sections, stepStory } from "./stories";

const story = (id: string, kind: Story["kind"], extra: Partial<Story> = {}): Story => ({
  id, kind, title: id, summary: "", text_source: "template", risk: null, counts: {}, nodes: [], flows: [], findings: [],
  board: null, cls: [], sub: null, subs: [], collapsed: false, ...extra,
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
    expect(sections(set([story("S1", "other"), story("S2", "unsorted")])).unsorted.map((x) => x.id)).toEqual(["S2"]);
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

  it("says a placement's reason in words, and a failed check as it is", () => {
    expect(reasonText("caller_of_new_code")).toBe("calls the new code");
    expect(reasonText("linked")).toBe("calls or shares data with the rest");
    expect(reasonText("target dsp differs from the story's (modem)")).toBe("target dsp differs from the story's (modem)");
  });

  it("lists the review's targets, and names a related story with its targets", () => {
    const ss = set([story("S1", "other", { targets: ["modem"] }), story("S2", "other", { targets: ["dsp", "modem"] }),
                    story("S3", "tests")]);
    expect(reviewTargets(ss)).toEqual(["dsp", "modem"]);
    expect(relatedLabel(ss, "S2")).toBe("S2 · dsp, modem");
    expect(relatedLabel(ss, "S9")).toBe("S9");
  });

  it("reads a citation as a node id or a file and line", () => {
    expect(citeTarget("N12")).toEqual({ node: "N12" });
    expect(citeTarget("drv/old.c:3")).toEqual({ file: "drv/old.c", line: 3 });
    expect(citeTarget("whatever")).toBeNull();
  });

  it("reads stories stored before two-tier stories: no targets, pieces or plan", () => {
    const old = set([story("S1", "behaviour"), story("S2", "other")]);    // none of the new fields
    expect(reviewTargets(old)).toEqual([]);
    expect(relatedLabel(old, "S1")).toBe("S1");
    expect(sections(old).unsorted).toEqual([]);
  });
});
