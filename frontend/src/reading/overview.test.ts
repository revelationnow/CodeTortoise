import { afterEach, describe, expect, it, vi } from "vitest";
import { keys } from "../board/prefs";
import { arcLayout, connectionRows, introOpen, routeRows, setIntroOpen, testsLine } from "./overview";
import type { Connection, RouteStep, TestsRow, Thread } from "./types";

const thread = (id: string, name = id): Thread => ({ id, name, purpose: "", text_source: "template", stories: [], cls: [], open_checks: 0 });
const conn = (a: string, b: string, kind: Connection["kind"] = "caller", shown = true, text = `${a}–${b}`): Connection =>
  ({ a, b, kind, text, facts: [], shown });
const T = ["T1", "T2", "T3", "T4"].map((id) => thread(id));

describe("how the threads connect", () => {
  it("draws only the shown connections, each from one thread box to the other", () => {
    const { arcs, height } = arcLayout(T, [conn("T1", "T2"), conn("T1", "T3", "place", false)], 60);
    expect(arcs.map((a) => [a.a, a.b, a.y1, a.y2])).toEqual([["T1", "T2", 30, 90]]);
    expect(height).toBe(240);
  });

  it("nests an arc around the arcs it spans, and arcs that only touch share a depth", () => {
    const { arcs, reach } = arcLayout(T, [conn("T1", "T3"), conn("T1", "T2"), conn("T2", "T3")], 60);
    const depth = Object.fromEntries(arcs.map((a) => [`${a.a}${a.b}`, a.depth]));
    expect(depth).toEqual({ T1T2: 1, T2T3: 1, T1T3: 2 });
    expect(reach).toBe(2 * 28);
    const outer = arcs.find((a) => a.depth === 2)!;
    expect(outer.d).toBe("M 0 30 C 56 30, 56 150, 0 150");
  });

  it("dashes the arc of threads joined only by their bundle", () => {
    const { arcs } = arcLayout(T, [conn("T2", "T4", "bundled")], 60);
    expect(arcs[0].dashed).toBe(true);
  });

  it("keeps the labels apart when two arcs meet at the same height", () => {
    const { arcs } = arcLayout(T, [conn("T1", "T4"), conn("T2", "T3")], 60);
    expect(arcs.map((a) => (a.y1 + a.y2) / 2)).toEqual([120, 120]);
    const ys = arcs.map((a) => a.labelY).sort((x, y) => x - y);
    expect(ys[1] - ys[0]).toBeGreaterThanOrEqual(20);
  });

  it("says each shown connection as a sentence row, for phones", () => {
    const rows = connectionRows(T, [conn("T1", "T2", "caller", true, "both run inside `main`"),
                                    conn("T2", "T4", "bundled", true, "nothing besides arriving in CL 104"),
                                    conn("T1", "T3", "place", false)]);
    expect(rows).toEqual([{ text: "A and B: both run inside `main`", bundled: false },
                          { text: "B and D: nothing besides arriving in CL 104 — ask the author", bundled: true }]);
  });
});

describe("the Tests row", () => {
  const tests = (covers: string[], untested: string[]): TestsRow => ({ stories: ["S9"], functions: 6, covers, untested });
  it("says which threads the tests cover and which nothing tests", () => {
    expect(testsLine(tests(["T1", "T2"], ["T3"]), T)).toBe("Tests: 6 cover threads A and B · nothing tests C");
    expect(testsLine(tests(["T1"], []), T)).toBe("Tests: 6 cover thread A");
    expect(testsLine(tests([], ["T1", "T2", "T3"]), T)).toBe("Tests: 6 · nothing tests A, B and C");
  });
});

describe("the introduction", () => {
  afterEach(() => vi.unstubAllGlobals());
  const step = (thread: string, reason = `why ${thread}`, skim = false): RouteStep => ({ thread, reason, skim });
  const threads = [{ ...thread("T1", "`send` changes"), stories: ["S2", "S1"] }, thread("T2", "init"), thread("T3", "step")];

  it("lists the route in its own order, lettering each thread by its place in the threads", () => {
    const rows = routeRows({ threads, route: [step("T3", "only bundled", true), step("T1"), step("T2")] });
    expect(rows.map((r) => [r.letter, r.name, r.reason, r.skim, r.first])).toEqual([
      ["C", "step", "only bundled", true, null], ["A", "`send` changes", "why T1", false, "S2"], ["B", "init", "why T2", false, null]]);
  });

  it("drops a step naming no thread of the reading, and has no rows for a reading stored before the route", () => {
    expect(routeRows({ threads, route: [step("T9"), step("T2")] }).map((r) => r.id)).toEqual(["T2"]);
    expect(routeRows({ threads })).toEqual([]);
  });

  it("opens the explainer on a first visit and keeps it closed once closed", () => {
    const store = new Map<string, string>();
    vi.stubGlobal("window", { localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) } });
    expect(introOpen()).toBe(true);
    setIntroOpen(false);
    expect(store.get(keys.introOpen)).toBe("false");
    expect(introOpen()).toBe(false);
    setIntroOpen(true);
    expect(introOpen()).toBe(true);
  });

  it("opens the explainer when storage is missing or throws, and closing it never throws", () => {
    expect(introOpen()).toBe(true);                                   // no window at all (node)
    vi.stubGlobal("window", { localStorage: { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("quota"); } } });
    expect(introOpen()).toBe(true);
    expect(() => setIntroOpen(false)).not.toThrow();
  });
});
