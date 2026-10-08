import { describe, expect, it } from "vitest";
import { lineDiff } from "../board/codeRows";
import { chipsAll, chipsOne } from "./sequence";
import type { FileLines } from "./types";

/** Base a b; CL 101 adds x1 x2 after a; CL 102 replaces them with z and adds y at the end; CL 102 also removes b. */
const fl: FileLines = {
  depot: "//d/f.c", local: "/w/f.c",
  wrote: [null, 102, 102], over: [null, 101, null], removed: [null, 102],
  rewritten: { "101": { "2": 102, "3": 102 } }, replaced: [], gaps: [],
};

const shown = (tags: ReturnType<typeof chipsAll>) =>
  [...tags.entries()].map(([k, t]) => [k, t.chip ? t.label : null, t.short, t.grey, t.cl]);

describe("CL chips (spec 2026-10-07-review-reading-phase2 §5)", () => {
  it("in the combined diff, chip each run of rows one CL wrote, saying when it replaced an earlier CL's lines", () => {
    const rows = lineDiff("a\nb\n", "a\nz\ny\n");
    expect(shown(chipsAll(rows, fl))).toEqual([
      ["old:2", "CL 102", "102", false, 102],
      ["new:2", "CL 102 · rewrites CL 101", "102", false, 102],
      ["new:3", "CL 102", "102", false, 102],
    ]);
  });

  it("leaves rows no CL of the review wrote without a chip", () => {
    const outside: FileLines = { ...fl, wrote: [null, null, null], over: [null, null, null], removed: [null, null] };
    expect(chipsAll(lineDiff("a\nb\n", "a\nz\ny\n"), outside).size).toBe(0);
  });

  it("in one CL's diff, greys its lines a later CL replaced and chips the first of each run", () => {
    const rows = lineDiff("a\nb\n", "a\nx1\nx2\nb\n");                // CL 101's own diff
    expect(shown(chipsOne(rows, fl, 101))).toEqual([
      ["new:2", "rewritten in CL 102", "→102", true, 102],
      ["new:3", null, "→102", true, 102],
    ]);
    expect(chipsOne(rows, fl, 102).size).toBe(0);
  });
});
