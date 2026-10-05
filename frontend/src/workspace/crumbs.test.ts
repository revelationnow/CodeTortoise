import { describe, expect, it } from "vitest";
import type { Finding } from "../api";
import type { Story } from "../board/types";
import { type CrumbContext, crumbs, short } from "./crumbs";

const ctx: CrumbContext = {
  base: "/r/7", title: "Review 7",
  stories: [{ id: "S1", title: "`frame_pop` writes `pool->free` from two threads at once" } as Story],
  findings: [{ id: "F2", title: "uart_send: new return value(s) -2" } as Finding],
  cls: [{ cl: 101, description: "uart: count tx stats\n\nlonger text" }],
  clusters: [{ id: "C1", name: "driver/uart" }],
};

describe("the breadcrumb", () => {
  it("names the review alone at home", () => {
    expect(crumbs({ kind: "whole" }, ctx)).toEqual([{ label: "Review 7", to: null }]);
  });

  it("goes up from a story's graph to its steps, the stories and the review", () => {
    expect(crumbs({ kind: "story", sid: "S1", view: "graph" }, ctx)).toEqual([
      { label: "Review 7", to: "/r/7" },
      { label: "Stories", to: "/r/7#stories" },
      { label: "frame_pop writes pool->free from two threads…", handle: "S1", to: "/r/7/s/S1" },
      { label: "Graph", to: null },
    ]);
    expect(crumbs({ kind: "story", sid: "S1", view: "steps" }, ctx).at(-1)).toEqual(
      { label: "frame_pop writes pool->free from two threads…", handle: "S1", to: null });
  });

  it("names findings, changelists and clusters under their sections", () => {
    expect(crumbs({ kind: "finding", fid: "F2" }, ctx).slice(1)).toEqual([
      { label: "Findings", to: "/r/7#findings" }, { label: "uart_send: new return value(s) -2", handle: "F2", to: null }]);
    expect(crumbs({ kind: "cl", cl: 101 }, ctx).slice(1)).toEqual([
      { label: "Change set", to: "/r/7#changeset" }, { label: "CL 101 · uart: count tx stats", to: null }]);
    expect(crumbs({ kind: "cluster", cid: "C1" }, ctx).slice(1)).toEqual([
      { label: "Map", to: "/r/7#map" }, { label: "driver/uart", to: null }]);
  });

  it("says when the item does not exist", () => {
    expect(crumbs({ kind: "story", sid: "S9", view: "steps" }, ctx).at(-1)).toEqual({ label: "Not found", to: null });
    expect(crumbs({ kind: "unknown", path: "/x" }, ctx).at(-1)).toEqual({ label: "Not found", to: null });
  });
});

describe("short", () => {
  it("drops backticks and cuts long text at a word", () => {
    expect(short("`a` b")).toBe("a b");
    expect(short("one two three four", 10)).toBe("one two…");
  });
});
