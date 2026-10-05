import { describe, expect, it } from "vitest";
import type { Address } from "./address";
import { recall, remember } from "./memory";

const story: Address = { place: { kind: "story", sid: "S1", view: "graph" }, flow: 2, open: { node: "N9" }, tab: "neighbours" };

describe("per-item memory", () => {
  it("returns to an item at its last view, flow and detail content", () => {
    const m = remember({}, story);
    expect(recall(m, { kind: "story", sid: "S1", view: "steps" })).toEqual(story);
  });

  it("opens an item it has not seen at its defaults", () => {
    expect(recall({}, { kind: "finding", fid: "F2" })).toEqual({ place: { kind: "finding", fid: "F2" }, flow: null, open: null, tab: "diff" });
  });

  it("keeps each item apart and the latest visit of each", () => {
    let m = remember({}, story);
    m = remember(m, { place: { kind: "finding", fid: "F2" }, flow: null, open: { file: "//d/a.c", line: 3 }, tab: "diff" });
    m = remember(m, { ...story, flow: 1, open: null });
    expect(recall(m, { kind: "story", sid: "S1", view: "steps" })).toEqual({ ...story, flow: 1, open: null });
    expect(recall(m, { kind: "finding", fid: "F2" }).open).toEqual({ file: "//d/a.c", line: 3 });
  });

  it("forgets nothing it was not told and ignores unknown places", () => {
    const m = remember({}, { place: { kind: "unknown", path: "/x" }, flow: 1, open: null, tab: "diff" });
    expect(m).toEqual({});
  });
});
