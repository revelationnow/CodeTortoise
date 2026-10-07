import { describe, expect, it } from "vitest";
import { indexFor, legacy } from "./legacy";

const q = (s: string) => new URLSearchParams(s);
const ctx = { base: "/r/7", nodeStory: { N9: "S1" } as Record<string, string>, oneBoard: true };

describe("old addresses", () => {
  it("send the old tabs to their places", () => {
    expect(legacy("/board", q(""), ctx)).toEqual({ to: "/r/7?view=graph" });
    expect(legacy("/board", q(""), { ...ctx, oneBoard: false })).toEqual({ to: "/r/7#map" });
    expect(legacy("/overview", q(""), ctx)).toEqual({ to: "/r/7#map" });
    expect(legacy("/findings", q(""), ctx)).toEqual({ to: "/r/7#findings" });
    expect(legacy("/cls", q(""), ctx)).toEqual({ to: "/r/7#changeset" });
    expect(legacy("/files", q(""), ctx)).toEqual({ to: "/r/7#files" });
  });

  it("open the item holding ?node=, with the node open", () => {
    expect(legacy("", q("node=N9"), ctx)).toEqual({ to: "/r/7/s/S1?open=N9" });
    expect(legacy("/board", q("node=N9"), ctx)).toEqual({ to: "/r/7/s/S1?open=N9" });
    expect(legacy("/c/C2", q("node=N4&x=N4:callers"), ctx)).toEqual({ to: "/r/7/c/C2?open=N4" });
    expect(legacy("", q("node=N4"), ctx)).toEqual({ to: "/r/7?view=graph&open=N4" });
    expect(legacy("", q("node=N4"), { ...ctx, oneBoard: false })).toEqual({ locate: "N4" });
  });

  it("rename the old story tab and cluster file parameters", () => {
    expect(legacy("/s/S1", q("tab=graph"), ctx)).toEqual({ to: "/r/7/s/S1?view=graph" });
    expect(legacy("/c/C1", q("file=//d/a.c"), ctx)).toEqual({ to: "/r/7/c/C1?open=file%3A%2F%2Fd%2Fa.c" });
    expect(legacy("/c/C1", q("x=N4:callers"), ctx)).toEqual({ to: "/r/7/c/C1" });       // the old expand state: dropped
    expect(legacy("/s/S1", q("x=N4:callers&flow=2"), ctx)).toEqual({ to: "/r/7/s/S1?flow=2" });
  });

  it("leave current addresses alone", () => {
    expect(legacy("/s/S1", q("view=graph&open=N9&tab=neighbours"), ctx)).toBeNull();
    expect(legacy("", q(""), ctx)).toBeNull();
  });
});

describe("the old sections' anchors", () => {
  it("open the Index's tabs once the review has a reading", () => {
    expect(["map", "findings", "changeset", "files", "stories", "x"].map(indexFor)).toEqual([
      { kind: "index", tab: "map" }, { kind: "index", tab: "checks" }, { kind: "index", tab: "cls" }, { kind: "index", tab: "files" },
      null, null]);
  });
});
