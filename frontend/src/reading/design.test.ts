import { describe, expect, it } from "vitest";
import { alsoLine, blockLine, componentBands, conditionTitle, foldGate, gateGroups, showsWhere } from "./design";
import type { Component, Gate, GatedLine } from "./types";

const comp = (o: Partial<Component>): Component => ({
  name: "x", level: null, band: "other", globs: [], threads: [], stories: [], files: [], crossing: [], quiet: false, ...o });
const line = (runs: boolean, o: Partial<GatedLine> = {}): GatedLine => ({
  story: "S1", cl: 101, text: "st->tx++;", runs, where: runs ? "outside" : "under", path: "driver/uart.c", line: 22,
  function: "uart_send", ...o });
const gate = (o: Partial<Gate>): Gate => ({
  id: "G1", node: "N3", test: "len > 64", false_case: "", lines: [], source: "code", story: "S1", path: "driver/uart.c", line: 16,
  guarded: [16, 19], runs: 0, stops: 0, ...o });
const T = [{ id: "T1" }, { id: "T2" }];

describe("Where the change sits (spec 2026-11-02 §5)", () => {
  it("shows with two components or more", () => {
    expect(showsWhere(null)).toBe(false);
    expect(showsWhere({ components: [comp({})] })).toBe(false);
    expect(showsWhere({ components: [comp({}), comp({ name: "y" })] })).toBe(true);
  });

  it("bands the components by layer, the highest first and those without a level last, each band in the design's order", () => {
    const cs = [comp({ name: "x" }), comp({ name: "service", level: 3, band: "service" }),
                comp({ name: "cpp", level: 0, band: "cpp, include/hal" }), comp({ name: "include/hal", level: 0, band: "cpp, include/hal" }),
                comp({ name: "driver", level: 2, band: "driver" })];
    expect(componentBands(cs).map((b) => [b.band, b.level, b.components.map((c) => c.name)])).toEqual([
      ["service", 3, ["service"]], ["driver", 2, ["driver"]], ["cpp, include/hal", 0, ["cpp", "include/hal"]], ["other", null, ["x"]]]);
  });

  it("counts a block's threads by letter and its changed files, and names two of its stories", () => {
    expect(blockLine(comp({ threads: ["T1"], files: ["driver/uart.c", "driver/uart.h"] }), T)).toBe("Thread A · 2 changed files");
    expect(blockLine(comp({ threads: ["T2", "T1", "T9"], files: ["a.c"] }), T)).toBe("Threads B and A · 1 changed file");
    expect(blockLine(comp({}), T)).toBe("");
    const titles: Record<string, string> = { S1: "`uart_send` drops long writes", S2: "`hal_write` takes an int", S3: "levels" };
    const title = (s: string) => titles[s];
    expect(alsoLine(["S1", "S9", "S2", "S3"], title)).toBe("`uart_send` drops long writes; `hal_write` takes an int; and 1 more");
    expect(alsoLine(["S1"], title)).toBe("`uart_send` drops long writes");
    expect(alsoLine([], title)).toBe("");
  });
});

describe("the condition fold (§7)", () => {
  it("is about the strongest condition, when it has lines", () => {
    const g = gate({ lines: [line(true)] });
    expect(foldGate(null)).toBeNull();
    expect(foldGate({ gates: [] })).toBeNull();
    expect(foldGate({ gates: [gate({})] })).toBeNull();
    expect(foldGate({ gates: [g, gate({ id: "G2" })] })).toBe(g);
  });

  it("is titled by the false case and the changes that still run, and lists those, then the ones that stop", () => {
    expect(conditionTitle({ false_case: "", test: "len > 64", runs: 9 })).toBe("When `len > 64` is false · 9 changes still run");
    expect(conditionTitle({ false_case: "Writes that fit (64 bytes or less)", test: "len > 64", runs: 1 }))
      .toBe("Writes that fit (64 bytes or less) · 1 change still runs");
    expect(conditionTitle({ false_case: "", test: "a `b`", runs: 0 })).toBe("When `a 'b'` is false · 0 changes still run");
    const runs = [line(true, { line: 14 }), line(true, { line: 22 })], stops = [line(false, { line: 17 })];
    expect(gateGroups(gate({ lines: [runs[0], stops[0], runs[1]] }))).toEqual({ runs, stops });
  });
});
