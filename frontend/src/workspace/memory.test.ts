import { afterEach, describe, expect, it, vi } from "vitest";
import type { Address } from "./address";
import { loadMemory, recall, remember, saveMemory } from "./memory";

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

describe("a lit story", () => {
  it("is not remembered: the map opens plain next time", () => {
    const a: Address = { place: { kind: "whole", view: "graph" }, flow: 2, open: null, tab: "diff", story: "S1" };
    expect(recall(remember({}, a), { kind: "whole" })).toEqual({ place: { kind: "whole", view: "graph" }, flow: 2, open: null, tab: "diff" });
  });
});

describe("stored memory", () => {
  afterEach(() => vi.unstubAllGlobals());
  const storage = (items: Record<string, string> = {}) => {
    vi.stubGlobal("window", { sessionStorage: {
      getItem: (k: string) => items[k] ?? null, setItem: (k: string, v: string) => { items[k] = v; } } });
    return items;
  };

  it("survives a reload, one review apart from another", () => {
    const items = storage();
    saveMemory(7, remember({}, story));
    expect(loadMemory(7)).toEqual({ "s:S1": story });
    expect(loadMemory(8)).toEqual({});
    expect(Object.keys(items)).toEqual(["ct.ws.7.memory"]);
  });

  it("drops stored entries that are not addresses, or not at their own item", () => {
    const finding: Address = { place: { kind: "finding", fid: "F2" }, flow: null, open: { file: "//d/a.c", line: null }, tab: "diff" };
    storage({ "ct.ws.7.memory": JSON.stringify({
      "s:S1": story, "f:F2": finding,
      "f:F3": { place: { kind: "finding", fid: "F9" }, flow: null, open: null, tab: "diff" },     // filed under another item
      "s:S2": { place: { kind: "story", sid: "S2", view: "sideways" }, flow: null, open: null, tab: "diff" },
      "s:S3": { place: { kind: "story", sid: "S3", view: "steps" }, flow: -1, open: null, tab: "diff" },
      "s:S4": { place: { kind: "story", sid: "S4", view: "steps" }, flow: null, open: { node: 4 }, tab: "diff" },
      "s:S5": { place: { kind: "story", sid: "S5", view: "steps" }, flow: null, open: null, tab: "nope" },
      "cl:1": "CL 1", "whole": null }) });
    expect(loadMemory(7)).toEqual({ "s:S1": story, "f:F2": finding });
  });

  it("forgets when storage is unreadable or throws", () => {
    storage({ "ct.ws.7.memory": "{not json" });
    expect(loadMemory(7)).toEqual({});
    vi.stubGlobal("window", { sessionStorage: { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } } });
    expect(loadMemory(7)).toEqual({});
    expect(() => saveMemory(7, {})).not.toThrow();
  });
});
