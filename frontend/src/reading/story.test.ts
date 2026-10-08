import { describe, expect, it } from "vitest";
import { byEntry, clCounts, clRewrites, codeOrder, foldPath, readOrder, rewriteText, stepIn, threadCrumb, whereByCl, whereTree } from "./story";
import type { CallPath, ContractRow, Reading, Rewrite, WhereFile } from "./types";

const fn = (node: string, label: string, cl: number | null, extra = {}) => ({ node, label, add: 2, rem: 1, cl, line: 3, ...extra });
const file = (path: string, functions: ReturnType<typeof fn>[]): WhereFile => ({ path, depot: `//d/${path}`, functions });
const path = (labels: string[], extra: Partial<CallPath> = {}): CallPath => ({
  steps: labels.map((l) => `n-${l}`), labels, kind: "call", entry: `n-${labels[0]}`, hidden: [], text: "", flow: null, ...extra,
});

describe("a story's place", () => {
  it("steps through every story in reading order, wrapping", () => {
    const order = ["S2", "S1", "S3"];
    expect(stepIn(order, "S2", 1)).toBe("S1");
    expect(stepIn(order, "S2", -1)).toBe("S3");
    expect(stepIn(order, "S3", 1)).toBe("S2");
    expect(stepIn(order, "S9", 1)).toBe("S9");
  });

  it("names its thread and its place in it", () => {
    const r = { threads: [{ id: "T1", name: "a", stories: ["S2", "S1"] }, { id: "T2", name: "`b` in x", stories: ["S3"] }] } as Reading;
    expect(threadCrumb(r, "S1")).toEqual({ letter: "A", name: "a", id: "T1", text: "story 2 of 2" });
    expect(threadCrumb(r, "S3")).toEqual({ letter: "B", name: "`b` in x", id: "T2", text: "story 1 of 1" });
    expect(threadCrumb(r, "S5")).toBeNull();
  });
});

describe("Where", () => {
  it("counts each CL's changed functions for the header chips", () => {
    expect(clCounts([file("a/x.c", [fn("N1", "f", 12), fn("N2", "g", 11)]), file("a/y.c", [fn("N3", "h", 12), fn("N4", "k", null)])]))
      .toEqual([{ cl: 11, functions: 1 }, { cl: 12, functions: 2 }]);
  });

  it("goes folder, file, functions, and shows a function's CL only where its file was edited in several", () => {
    const tree = whereTree([file("drv/uart.c", [fn("N1", "send", 101), fn("N2", "init", 102)]), file("drv/hal.c", [fn("N3", "w", 102)]),
                            file("top.c", [fn("N4", "main", 101)])]);
    expect(tree.map((d) => [d.dir, d.files.map((f) => [f.name, f.showCl])])).toEqual([
      ["drv", [["uart.c", true], ["hal.c", false]]], [".", [["top.c", false]]]]);
  });
});

describe("Call paths", () => {
  it("groups the paths under their entry point in rank order", () => {
    const groups = byEntry([path(["main", "flush", "send"]), path(["isr", "send"]), path(["main", "write", "send"]),
                            path(["worker", "send"], { entry: null })]);
    expect(groups.map((g) => [g.label, g.entry, g.paths.length])).toEqual([["main", true, 2], ["isr", true, 1], ["worker", false, 1]]);
  });

  it("folds the middle of a long path into one step until it is opened", () => {
    const p = path(["main", "a", "b", "c", "send"], { hidden: ["n-a", "n-b"] });
    expect(foldPath(p, false)).toEqual([{ label: "main" }, { more: 2 }, { label: "c" }, { label: "send" }]);
    expect(foldPath(p, true).map((s) => ("label" in s ? s.label : s.more))).toEqual(["main", "a", "b", "c", "send"]);
  });
});

describe("Code", () => {
  it("shows the functions whose contract changed first, then the rest in Where's order", () => {
    const where = [file("a.c", [fn("N1", "caller", 1), fn("N2", "callee", 1)]), file("b.c", [fn("N3", "other", 1)])];
    const rows = [{ kind: "signature", nodes: ["N2"] } as ContractRow, { kind: "body", nodes: ["N1", "N3"] } as ContractRow];
    expect(codeOrder(where, rows).map((f) => f.label)).toEqual(["callee", "caller", "other"]);
  });
});

describe("CLs as a sequence (spec 2026-10-07-review-reading-phase2 §5.3, §5.4)", () => {
  const w = (path: string, cls: number[]) => ({ ...file(path, [fn(`n-${path}`, path, cls[0] ?? null)]), cls });
  const rw = (by: number, of: number, fnName: string | null, lines: number, file = "//d/drv/uart.c"): Rewrite =>
    ({ by, of, file, function: fnName, lines, line: lines ? 4 : null });

  it("groups Where's files under the first of the story's CLs that edits them, in reading order, naming the others", () => {
    const groups = whereByCl([w("a.c", [103]), w("b.c", [101, 103]), w("c.c", [101]), w("d.c", [])], [101, 103]);
    expect(groups.map((g) => [g.cl, g.files.map((f) => [f.path, f.also])])).toEqual([
      [101, [["b.c", [103]], ["c.c", []]]], [103, [["a.c", []]]], [null, [["d.c", []]]]]);
  });

  it("says the order to read a story's CLs in only when it has several", () => {
    expect(readOrder([101, 103, 105])).toBe("Read CL 101, then CL 103, then CL 105");
    expect(readOrder([104])).toBeNull();
    expect(readOrder(undefined)).toBeNull();
  });

  it("says what a rewrite replaced and where, by function or else by file", () => {
    expect(rewriteText(rw(103, 101, "uart_send", 5))).toEqual({ lead: "CL 103 rewrites 5 lines CL 101 added in", name: "uart_send" });
    expect(rewriteText(rw(105, 103, null, 1))).toEqual({ lead: "CL 105 rewrites 1 line CL 103 added in", name: "uart.c" });
  });

  it("splits the review's rewrites into a CL's two directions", () => {
    const all = [rw(103, 101, "send", 5), rw(105, 103, "init", 1), rw(104, 102, "x", 2)];
    expect(clRewrites(all, 103)).toEqual({ rewrites: [all[0]], rewrittenBy: [all[1]] });
    expect(clRewrites(undefined, 103)).toEqual({ rewrites: [], rewrittenBy: [] });
  });
});
