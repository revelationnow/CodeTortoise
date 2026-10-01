import { describe, expect, it } from "vitest";
import { codeItems, lineDiff, plainLines, sliceRange } from "./codeRows";
import type { Annotation } from "./types";

const before = "a\nb\nc\nd\n";
const after = "a\nB\nc\nx\nd\n";
const ann = (line: number, severity: Annotation["severity"] = "warn", side: Annotation["side"] = "new") =>
  ({ node: "N1", path: "//d/f.c", line, side, severity, channel: "state", title: "State", text: `at ${line}`,
     finding: null, cause: null, landing: false }) as Annotation;

describe("code rows", () => {
  it("numbers both sides of a diff", () => {
    expect(lineDiff(before, after).map((l) => `${l.t}${l.o ?? ""}/${l.n ?? ""}`))
      .toEqual(["=1/1", "-2/", "+/2", "=3/3", "+/4", "=4/5"]);
  });

  it("slices a function's range, keeping deletions made inside it", () => {
    const rows = sliceRange(lineDiff(before, after), 2, 3);
    expect(rows.map((l) => l.text)).toEqual(["b", "B", "c"]);
    expect(sliceRange(plainLines("1\n2\n3\n4"), 3, 9).map((l) => l.n)).toEqual([3, 4]);
  });

  it("puts annotations and the thread right under their line", () => {
    const items = codeItems(lineDiff(before, after), "unified", [ann(3), ann(2, "ok"), ann(2, "warn", "old")],
                            new Set(["new:3", "old:2"]));
    expect(items.map((i) => i.kind === "line" ? i.line.text : i.kind === "ann" ? `ann ${i.ann.side}${i.ann.line}`
                                                                              : i.kind === "thread" ? `thread ${i.side}${i.no}` : "?"))
      .toEqual(["a", "b", "ann old2", "thread old2", "B", "ann new2", "c", "ann new3", "thread new3", "x", "d"]);
    const c = items.find((i) => i.kind === "line" && i.line.text === "c");
    expect(c && c.kind === "line" && c.hot).toBe(true);           // warn on an unchanged line
  });

  it("pairs deletions with additions side by side", () => {
    const items = codeItems(lineDiff(before, after), "split", [ann(2)], new Set());
    const pairs = items.filter((i) => i.kind === "pair").map((i) => i.kind === "pair" ? `${i.l?.text ?? "_"}|${i.r?.text ?? "_"}` : "");
    expect(pairs).toEqual(["a|a", "b|B", "c|c", "_|x", "d|d"]);
    expect(items[2]).toMatchObject({ kind: "ann" });
  });
});

describe("windowing big files", () => {
  const big = plainLines(Array.from({ length: 5000 }, (_, i) => `line ${i + 1}`).join("\n"));

  it("shows everything for ordinary files", async () => {
    const { windowAround } = await import("./codeRows");
    expect(windowAround(plainLines("a\nb\nc"), [], null, { above: 0, below: 0 })).toEqual({ start: 0, end: 3 });
  });

  it("centres a window on the focus line, then the first change or annotation, and grows on request", async () => {
    const { windowAround, WINDOW } = await import("./codeRows");
    expect(windowAround(big, [], 2500, { above: 0, below: 0 })).toEqual({ start: 2499 - WINDOW, end: 2499 + WINDOW });
    expect(windowAround(big, [ann(4000)], null, { above: 0, below: 0 }).start).toBe(3999 - WINDOW);
    expect(windowAround(big, [], null, { above: 0, below: 0 })).toEqual({ start: 0, end: WINDOW });
    expect(windowAround(big, [], 2500, { above: 100, below: Infinity })).toEqual({ start: 2399 - WINDOW, end: 5000 });
  });
});
