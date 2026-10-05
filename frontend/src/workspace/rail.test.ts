import { describe, expect, it } from "vitest";
import type { Finding } from "../api";
import type { Story, StorySet } from "../board/types";
import { bySeverity, litStories, storyCls } from "./rail";

const story = (id: string, cls: number[]): Story => ({
  id, kind: "behaviour", title: id, summary: "", text_source: "template", risk: null, counts: {}, nodes: [], flows: [],
  findings: [], board: null, cls, sub: null, subs: [], collapsed: false,
});
const set = (stories: Story[]): StorySet => ({ summary: "", stories, node_story: {}, flow_story: {}, finding_story: {} });
const finding = (id: string, severity: Finding["severity"]): Finding => ({
  id, kind: "contract", severity, title: id, nodes: [], evidence: [], summary: "", explanation: null, verify_steps: [],
  hypotheses: [], state: "open", files: null,
});

describe("the rail's change set", () => {
  it("counts the CLs the stories come from", () => {
    expect(storyCls(set([story("S1", [101]), story("S2", [102, 101]), story("S3", [])]))).toEqual([101, 102]);
  });

  it("lights the stories drawn from the filtered CL; no filter lights none apart", () => {
    const ss = set([story("S1", [101]), story("S2", [102, 101]), story("S3", [102])]);
    expect(litStories(ss, 101)).toEqual(new Set(["S1", "S2"]));
    expect(litStories(ss, null)).toBeNull();
    expect(litStories(ss, 999)).toEqual(new Set());
  });
});

describe("the rail's findings", () => {
  it("group by severity, highest first, leaving out empty groups", () => {
    const g = bySeverity([finding("F1", "low"), finding("F2", "high"), finding("F3", "low"), finding("F4", "info")]);
    expect(g.map((x) => [x.severity, x.findings.map((f) => f.id)])).toEqual([["high", ["F2"]], ["low", ["F1", "F3"]], ["info", ["F4"]]]);
  });
});
