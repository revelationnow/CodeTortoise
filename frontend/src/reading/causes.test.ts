import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { alsoAt, around, causeGroups, causeOfCheck, causeOpen, doneCount, firstOpenAt, hiddenLabel, loadHidden, loadOutline, nextOpen,
  nextOpenAt, openCount, openPlaces, progressLine, saveHidden, saveOutline, shown } from "./causes";
import type { Cause, Check, CheckKind, Mark } from "./types";

const cause = (id: string, kind: CheckKind, story: string | null, places: string[], extra: Partial<Cause> = {}): Cause =>
  ({ id, kind, thread: "T1", story, text: `${id} text`, places, flows: [], finding: null, change: null, ...extra });
const mark = (key: string, changed = false): Mark => ({ key, user: "ana", at: "2026-10-16T10:00:00Z", source_line: "", changed });
const marks = (...keys: string[]) => Object.fromEntries(keys.map((k) => [k, mark(k)]));
const check = (key: string, path: string, line: number): Check =>
  ({ key, kind: "reader", story: "S1", thread: "T1", path, depot: null, line, function: null, node: null, text: key,
     source_line: "", finding: null, cites: [], cause: null });

// vitest runs in node here (no jsdom): a Map-backed localStorage, as overview.test.ts does
beforeEach(() => {
  const store = new Map<string, string>();
  vi.stubGlobal("window", { localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) } });
});
afterEach(() => vi.unstubAllGlobals());

describe("open places", () => {
  const c = cause("c1", "reader", "S1", ["a", "b", "c"]);
  it("a place is open until marked, and open again when its line changed", () => {
    expect(openPlaces(c, { a: mark("a"), b: mark("b", true) })).toEqual(["b", "c"]);
    expect(doneCount(c, { a: mark("a"), b: mark("b", true) })).toBe(1);
    expect(causeOpen(c, marks("a", "b", "c"))).toBe(false);
    expect(causeOpen(c, { ...marks("a", "c"), b: mark("b", true) })).toBe(true);
  });
  it("the first open place, 1-based; 1 when all are done", () => {
    expect(firstOpenAt(c, marks("a"))).toBe(2);
    expect(firstOpenAt(c, marks("a", "b", "c"))).toBe(1);
  });
  it("Skip and Back step over done places, wrapping, and find none when this is the only open one", () => {
    expect(nextOpenAt(c, marks("b"), 1, 1)).toBe(3);
    expect(nextOpenAt(c, marks("b"), 3, 1)).toBe(1);
    expect(nextOpenAt(c, marks("b"), 1, -1)).toBe(3);
    expect(nextOpenAt(c, marks("a", "b"), 3, 1)).toBeNull();
  });
});

describe("hidden kinds", () => {
  const all = [cause("c1", "confirm", "S1", ["a"]), cause("c2", "reader", "S1", ["b"]), cause("c3", "caller", "S2", ["c"])];
  it("hide Confirm by default and remember another choice", () => {
    expect([...loadHidden()]).toEqual(["confirm"]);
    saveHidden(new Set<CheckKind>(["reader", "caller"]));
    expect([...loadHidden()].sort()).toEqual(["caller", "reader"]);
    window.localStorage.setItem("ct.ws.hiddenKinds", JSON.stringify(["nonsense", 3]));
    expect([...loadHidden()]).toEqual([]);
    window.localStorage.setItem("ct.ws.hiddenKinds", "{not json");
    expect([...loadHidden()]).toEqual(["confirm"]);
  });
  it("leave hidden causes out of what is shown and counted", () => {
    expect(shown(all, new Set(["confirm"])).map((c) => c.id)).toEqual(["c2", "c3"]);
    expect(openCount(all, new Set(["confirm"]), marks("c"))).toBe(1);
  });
  it("name what they hide", () => {
    expect(hiddenLabel(new Set(), all)).toBe("Showing all");
    expect(hiddenLabel(new Set(["confirm"]), all)).toBe("Showing: all but Confirm · 1 hidden");
    expect(hiddenLabel(new Set(["confirm", "caller"]), all)).toBe("Showing: all but Confirm, Caller not updated · 2 hidden");
  });
});

describe("the outline's view", () => {
  it("is Stories unless the reader chose Checks", () => {
    expect(loadOutline()).toBe("stories");
    saveOutline("checks");
    expect(loadOutline()).toBe("checks");
    window.localStorage.setItem("ct.ws.outline", JSON.stringify("sideways"));
    expect(loadOutline()).toBe("stories");
  });
});

describe("Next open check", () => {
  const order = ["S2", "S1", "S3"];
  const all = [cause("c1", "caller", "S2", ["a"]), cause("c2", "confirm", "S2", ["b"]), cause("c3", "result", "S1", ["c", "d"]),
               cause("c4", "ask", null, ["e"])];
  const hidden = new Set<CheckKind>(["confirm"]);
  it("goes to the first open shown cause after the one in the panel, at its first open place, wrapping", () => {
    expect(nextOpen(all, hidden, marks("c"), { cause: "c1", order })).toEqual({ cause: "c3", at: 2 });
    expect(nextOpen(all, hidden, {}, { cause: "c4", order })).toEqual({ cause: "c1", at: 1 });
    expect(nextOpen(all, hidden, marks("a"), { cause: "c3", order })).toEqual({ cause: "c4", at: 1 });
  });
  it("without a cause in the panel starts at the current story, else at the start", () => {
    expect(nextOpen(all, hidden, {}, { story: "S1", order })).toEqual({ cause: "c3", at: 1 });
    expect(nextOpen(all, hidden, marks("c", "d"), { story: "S1", order })).toEqual({ cause: "c4", at: 1 });
    expect(nextOpen(all, hidden, {}, { order })).toEqual({ cause: "c1", at: 1 });
  });
  it("finds a done cause again once a marked line changed", () => {
    expect(nextOpen(all, hidden, { a: mark("a", true), ...marks("c", "d", "e") }, { order })).toEqual({ cause: "c1", at: 1 });
  });
  it("finds nothing when every shown cause is done or hidden", () => {
    expect(nextOpen(all, hidden, marks("a", "c", "d", "e"), { order })).toBeNull();
    expect(nextOpen(all, new Set(["caller", "confirm", "result", "ask"]), {}, { order })).toBeNull();
  });
});

describe("a check's cause", () => {
  const all = [cause("c1", "reader", "S1", ["a", "b"]), cause("c2", "confirm", "S1", ["x"], { finding: "F4" }),
               cause("c3", "result", "S1", ["z"])];
  it("is found by the check's key or by its finding", () => {
    expect(causeOfCheck(all, "b")).toEqual({ cause: all[0], at: 2 });
    expect(causeOfCheck(all, "F4")).toEqual({ cause: all[1], at: 1 });
    expect(causeOfCheck(all, "nope")).toBeNull();
  });
  it("other causes at the same place are listed with where that place is in them", () => {
    const checks = new Map([["a", check("a", "x.c", 3)], ["b", check("b", "y.c", 9)], ["x", check("x", "y.c", 9)],
                            ["z", check("z", "x.c", 4)]]);
    expect(alsoAt(all, checks, all[0], "b")).toEqual([{ cause: all[1], at: 1 }]);
    expect(alsoAt(all, checks, all[0], "a")).toEqual([]);
  });
});

describe("the header's progress", () => {
  it("counts stories read and the open causes", () => {
    expect(progressLine(3, 9, 12, 20)).toBe("3 of 9 stories read · 12 causes open");
    expect(progressLine(3, 9, 1, 20)).toBe("3 of 9 stories read · 1 cause open");
    expect(progressLine(9, 9, 0, 20)).toBe("9 of 9 stories read · every check done");
    expect(progressLine(0, 2, 0, 0)).toBe("0 of 2 stories read");
  });
});

describe("the Checks view's groups", () => {
  const threads = [{ id: "T1", name: "`hal_write` in hal", stories: ["S2", "S1"] }, { id: "T3", name: "cpp", stories: ["S4"] }];
  it("are threads, then stories in reading order, then causes of no story; no thread goes last", () => {
    const list = [cause("c1", "caller", "S2", ["a"]), cause("c2", "result", "S1", ["b"]),
                  cause("c3", "ask", null, ["c"], { thread: "T3" }), cause("c4", "target", null, ["d"], { thread: null })];
    expect(causeGroups({ threads } as never, list).map((g) => [g.label, g.stories.map((s) => [s.story, s.causes.map((c) => c.id)])]))
      .toEqual([["A · `hal_write` in hal", [["S2", ["c1"]], ["S1", ["c2"]]]], ["B · cpp", [[null, ["c3"]]]],
                ["Across the change", [[null, ["c4"]]]]]);
  });
});

describe("around", () => {
  it("gives the place's line with three lines each side, as far as the file goes", () => {
    const text = ["a", "b", "c", "d", "e", "f", "g", "h"].join("\n");
    expect(around(text, 5).map((l) => [l.line, l.text, l.at])).toEqual([[2, "b", false], [3, "c", false], [4, "d", false],
      [5, "e", true], [6, "f", false], [7, "g", false], [8, "h", false]]);
    expect(around(text, 1).map((l) => l.line)).toEqual([1, 2, 3, 4]);
    expect(around(text, 40)).toEqual([]);
  });
});
