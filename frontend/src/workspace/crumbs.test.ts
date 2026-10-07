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
    expect(crumbs({ kind: "whole", view: "graph" }, ctx)).toEqual([{ label: "Review 7", to: "/r/7" }, { label: "Graph", to: null }]);
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
      { label: "Findings", to: "/r/7#findings" }, { label: "uart_send: new return value -2", handle: "F2", to: null }]);
    expect(crumbs({ kind: "cl", cl: 101 }, ctx).slice(1)).toEqual([
      { label: "Change set", to: "/r/7#changeset" }, { label: "CL 101 · uart: count tx stats", to: null }]);
    expect(crumbs({ kind: "cluster", cid: "C1" }, ctx).slice(1)).toEqual([
      { label: "Map", to: "/r/7#map" }, { label: "driver/uart", to: null }]);
  });

  it("with a reading, puts a story under its thread and CLs, files, checks and the map under the Index", () => {
    const r = { ...ctx, threadOf: (sid: string) => (sid === "S1" ? "Thread A" : null) };
    const home = { label: "Review 7", to: "/r/7" };
    expect(crumbs({ kind: "story", sid: "S1", view: "steps" }, r)).toEqual([home, { label: "Thread A", to: "/r/7" },
      { label: "frame_pop writes pool->free from two threads…", handle: "S1", to: null }]);
    expect(crumbs({ kind: "cluster", cid: "C1" }, r)).toEqual([home, { label: "Map", to: "/r/7/i/map" }, { label: "driver/uart", to: null }]);
    expect(crumbs({ kind: "cl", cl: 101 }, r)).toEqual([home, { label: "CLs", to: "/r/7/i/cls" },
      { label: "CL 101 · uart: count tx stats", to: null }]);
    expect(crumbs({ kind: "finding", fid: "F2" }, r)).toEqual([home, { label: "Checks", to: "/r/7/i/checks" },
      { label: "uart_send: new return value -2", handle: "F2", to: null }]);
    expect(crumbs({ kind: "index", tab: "files" }, r)).toEqual([home, { label: "Files", to: null }]);
  });

  it("names a changelist without a description by number, and cuts a long one", () => {
    const c = { ...ctx, cls: [{ cl: 5, description: null }, { cl: 6, description: "  \n" },
                              { cl: 7, description: "uart: count tx stats, rx stats, framing errors and parity errors per port" }] };
    expect(crumbs({ kind: "cl", cl: 5 }, c).at(-1)).toEqual({ label: "CL 5", to: null });
    expect(crumbs({ kind: "cl", cl: 6 }, c).at(-1)).toEqual({ label: "CL 6", to: null });
    expect(crumbs({ kind: "cl", cl: 7 }, c).at(-1)).toEqual({ label: "CL 7 · uart: count tx stats, rx stats,…", to: null });
  });

  it("says when the item does not exist, under its section", () => {
    const missing = { label: "Not found", to: null };
    expect(crumbs({ kind: "story", sid: "S9", view: "steps" }, ctx).slice(1)).toEqual([{ label: "Stories", to: "/r/7#stories" }, missing]);
    expect(crumbs({ kind: "finding", fid: "F9" }, ctx).slice(1)).toEqual([{ label: "Findings", to: "/r/7#findings" }, missing]);
    expect(crumbs({ kind: "cl", cl: 999 }, ctx).slice(1)).toEqual([{ label: "Change set", to: "/r/7#changeset" }, missing]);
    expect(crumbs({ kind: "cluster", cid: "C9" }, ctx).slice(1)).toEqual([{ label: "Map", to: "/r/7#map" }, missing]);
    expect(crumbs({ kind: "unknown", path: "/x" }, ctx).at(-1)).toEqual(missing);
  });

  it("hands out a crumb the caller may change without changing the next one", () => {
    const a = crumbs({ kind: "unknown", path: "/x" }, ctx).at(-1)!;
    a.label = "changed";
    expect(crumbs({ kind: "unknown", path: "/y" }, ctx).at(-1)).toEqual({ label: "Not found", to: null });
  });
});

describe("short", () => {
  it("drops backticks and cuts long text at a word", () => {
    expect(short("`a` b")).toBe("a b");
    expect(short("one two three four", 10)).toBe("one two…");
  });
});
