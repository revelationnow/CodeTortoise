import { describe, expect, it } from "vitest";
import { alsoLine, blockLine, byModel, citeName, componentBands, concernWhere, conditionTitle, foldGate, gateGroups,
  OWNER_TAG, ownershipTitle, showsWhere, storyConcerns, verdictCauses } from "./design";
import type { Cause, Component, Gate, GatedLine } from "./types";

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

const cause = (id: string): Cause => ({ id, kind: "result", thread: "T1", story: "S1", text: id, places: [], flows: [], finding: null, change: null });

describe("the model's parts (spec 2026-11-02 §3.1, §6)", () => {
  it("chips the causes the verdict names that the review has, in the verdict's order", () => {
    const causes = [cause("c1"), cause("c2"), cause("c3")];
    expect(verdictCauses({ verdict_causes: ["c3", "c9", "c1"] }, causes).map((c) => c.id)).toEqual(["c3", "c1"]);
    expect(verdictCauses({ verdict_causes: ["c1"] }, null)).toEqual([]);
  });

  it("titles the ownership fold by its questionable lines and shortfalls", () => {
    expect(ownershipTitle([{ tag: "right" }, { tag: "questionable" }, { tag: "shortfall" }, { tag: "shortfall" }]))
      .toBe("Is the design right? · 1 questionable · 2 shortfalls");
    expect(ownershipTitle([{ tag: "questionable" }])).toBe("Is the design right? · 1 questionable");
    expect(ownershipTitle([{ tag: "right" }, { tag: "note" }])).toBe("Is the design right? · nothing questionable");
    expect(OWNER_TAG).toEqual({ right: "right", questionable: "confirm", shortfall: "shortfall", note: "note" });
  });

  it("places a concern by its stories' thread letters, each once, then its stories", () => {
    const threads = [{ id: "T1", stories: ["S2", "S1"] }, { id: "T2", stories: ["S3"] }];
    expect(concernWhere(["S1", "S3", "S2"], threads)).toEqual({ letters: ["A", "B"], stories: ["S1", "S3", "S2"] });
    expect(concernWhere(["S9"], threads)).toEqual({ letters: [], stories: ["S9"] });
  });

  it("numbers the concerns a story answers, as its crumb cites them", () => {
    const c = (stories: string[]) => ({ text: "t", how: "h", stories, assessment: "right" as const, note: "", causes: [] });
    const d = { concerns: [c(["S1"]), c(["S2"]), c(["S2", "S1"])] };
    expect([storyConcerns(d, "S1"), storyConcerns(d, "S2"), storyConcerns(d, "S3"), storyConcerns(null, "S1")])
      .toEqual([[1, 3], [2, 3], [], []]);
  });

  it("says which parts the model wrote, and names a cited node", () => {
    const d = { sources: { verdict: "llm", "gate:G1": "pinned", "walk:W1": "template" } as Record<string, "template" | "llm" | "pinned">,
                nodes: { N3: { label: "logger_flush", kind: "function" as const, component: "service", path: "service/logger.c", line: 20 } } };
    expect([byModel(d, "verdict"), byModel(d, "gate:G1"), byModel(d, "walk:W1"), byModel(d, "concerns"), byModel(null, "verdict")])
      .toEqual([true, true, false, false, false]);
    expect([citeName(d, "N3"), citeName(d, "S1"), citeName(d, "driver/uart.c")]).toEqual(["logger_flush", "S1", "driver/uart.c"]);
  });
});
