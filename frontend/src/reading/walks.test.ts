import { describe, expect, it } from "vitest";
import type { Check, CheckKind, Mark, ReadingDesign, Walk, WalkStep } from "./types";
import { CH, COL, connectionWalk, FRAME, flowSteps, LEFT, openSteps, PAD, ROW, stepKeys, stepList, stepRef, stepSentence, storyWalks,
         threadName, TOP, walkLayout, walkOpen, walkScope, walksForThread, walkThreads } from "./walks";

const step = (o: Partial<WalkStep>): WalkStep => ({
  kind: "call", src: "N1", dst: "N2", label: "", status: "same", ref: "code", story: null, flow: null, flow_n: null, cause: null,
  keys: [], edge: null, loop: null, path: "", line: null, cl: null, folded: 0, ...o });
const walk = (o: Partial<Walk>): Walk => ({
  id: "W1", title: "When `len > 64`", title_source: "template", lead: "", thread: "T1", connection: null, condition: null,
  case: null, parts: [], stories: [], steps: [], ...o });
const check = (key: string, kind: CheckKind, cause: string | null): Check => ({
  key, kind, story: "S1", thread: "T1", path: "driver/uart.c", depot: null, line: 1, function: null, node: null, text: "",
  source_line: "", finding: null, cites: [], cause });
const mark = (key: string, changed = false): Mark => ({ key, user: "demo", at: "", source_line: "", changed });
const T = [{ id: "T1" }, { id: "T2" }, { id: "T3" }];
const names: Record<string, string> = { N1: "main", N2: "logger_flush", N3: "uart_send", N4: "uart_errors", F1: "Uart::errors" };
const label = (n: string) => names[n] ?? "a function";

describe("a walk-through's threads (spec 2026-11-02 §3.2)", () => {
  it("names its own thread first, then the other end of its connection", () => {
    expect(walkScope(walk({ thread: "T1", connection: ["T1", "T2"] }), T)).toBe("Thread A with Thread B");
    expect(walkScope(walk({ thread: "T2", connection: ["T1", "T2"] }), T)).toBe("Thread B with Thread A");
    expect(walkScope(walk({ thread: "T3" }), T)).toBe("Thread C");
    expect(walkScope(walk({ thread: null }), T)).toBe("");
    expect(walkScope(walk({ thread: "T9", connection: ["T9", "T2"] }), T)).toBe("Thread B");   // a thread the reading no longer has
    expect(walkThreads(walk({ thread: "T2", connection: ["T1", "T2"] }))).toEqual(["T2", "T1"]);
    expect(threadName(T, "T9")).toBeNull();
  });
});

describe("a walk-through's checks (§4.3)", () => {
  const checks = new Map([check("result|a.c|f|g", "result", "c1"), check("caller|b.c|h|g", "caller", "c1"),
                          check("reader|a.c|r|g", "reader", "c2"), check("confirm|a.c|f|", "confirm", "c3")].map((k) => [k.key, k]));
  const w = walk({ steps: [step({ keys: ["result|a.c|f|g", "caller|b.c|h|g"] }), step({}), step({ keys: ["reader|a.c|r|g", "gone|x.c|y|z"] }),
                           step({ keys: ["confirm|a.c|f|"] })] });
  const hidden = new Set<CheckKind>(["confirm"]);

  it("ticks only the keys the reading still holds, of the kinds shown", () => {
    expect(stepKeys(w.steps[2], checks, hidden)).toEqual(["reader|a.c|r|g"]);
    expect(stepKeys(w.steps[3], checks, hidden)).toEqual([]);
    expect(stepKeys(w.steps[3], checks, new Set())).toEqual(["confirm|a.c|f|"]);
  });

  it("counts the distinct causes still open among its steps", () => {
    expect(walkOpen(w, checks, hidden, {})).toBe(2);                                   // c1 (at two places) and c2
    expect(walkOpen(w, checks, hidden, { "result|a.c|f|g": mark("result|a.c|f|g") })).toBe(2);   // c1 is still open at its caller row
    expect(walkOpen(w, checks, hidden, { "result|a.c|f|g": mark("result|a.c|f|g"), "caller|b.c|h|g": mark("caller|b.c|h|g") })).toBe(1);
    expect(walkOpen(w, checks, hidden, { "reader|a.c|r|g": mark("reader|a.c|r|g", true) })).toBe(2);   // its line changed since: open
    expect(walkOpen(w, checks, new Set(), {})).toBe(3);                                // Confirm shown: c3 counts too
  });

  it("knows which steps have a check still open", () => {
    expect([...openSteps(w, checks, hidden, { "reader|a.c|r|g": mark("reader|a.c|r|g") })]).toEqual([1]);
    expect([...openSteps(w, checks, hidden, {})]).toEqual([1, 3]);
  });
});

describe("where the walk-throughs are listed and linked", () => {
  const d: Pick<ReadingDesign, "walks"> = { walks: [
    walk({ id: "W1", thread: "T1", connection: ["T1", "T2"], steps: [
      step({ ref: "path", story: "S1", flow: "FL1", flow_n: 1 }), step({ ref: "change", story: "S1" }),
      step({ ref: "flow", story: "S1", flow: "FL1", flow_n: 1 }), step({}), step({ ref: "flow", story: "S2", flow: "FL3", flow_n: 1 })] }),
    walk({ id: "W2", thread: "T1", steps: [step({ ref: "path", story: "S1", flow: "FL1", flow_n: 1 }),
                                           step({ ref: "flow", story: "S1", flow: "FL1", flow_n: 1 })] }),
    walk({ id: "W3", thread: "T2", steps: [step({ ref: "change", story: "S2" })] })] };

  it("lists under a thread its own walk-throughs and those on a connection to it, naming the other end", () => {
    expect(walksForThread(d, "T1").map((x) => [x.walk.id, x.other])).toEqual([["W1", "T2"], ["W2", null]]);
    expect(walksForThread(d, "T2").map((x) => [x.walk.id, x.other])).toEqual([["W1", "T1"], ["W3", null]]);
    expect(walksForThread(d, "T3")).toEqual([]);
    expect(connectionWalk(d, "T2", "T1")?.id).toBe("W1");
    expect(connectionWalk(d, "T1", "T3")).toBeNull();
    expect(connectionWalk(null, "T1", "T2")).toBeNull();
  });

  it("finds a story's steps on each walk-through, and a flow's steps (a flow step only)", () => {
    expect(storyWalks(d, "S1").map((x) => [x.walk.id, x.steps])).toEqual([["W1", [1, 2, 3]], ["W2", [1, 2]]]);
    expect(storyWalks(d, "S9")).toEqual([]);
    expect(flowSteps(d, "S1", "FL1").map((x) => [x.walk.id, x.n])).toEqual([["W1", 3], ["W2", 2]]);   // W2's step 1 is its call path
    expect(flowSteps(d, "S1", "FL3")).toEqual([]);                                     // FL3 is S2's
  });

  it("writes step numbers as runs, three or more joined", () => {
    expect(stepList([1, 2, 3, 4, 5, 8])).toBe("1–5, 8");
    expect(stepList([2, 3])).toBe("2, 3");
    expect(stepList([4])).toBe("4");
    expect(stepList([1, 3, 4, 5, 7, 8])).toBe("1, 3–5, 7, 8");
  });
});

describe("a step's line and where it comes from (§3.3)", () => {
  it("says each kind of step in the code's own words", () => {
    expect(stepSentence(step({ src: "N1", dst: "N2", label: "logger_flush(&g_log)" }), label)).toBe("`main` calls `logger_flush(&g_log)`");
    expect(stepSentence(step({ src: "N1", dst: "N2", label: "(*fp)(x)" }), label)).toBe("`main` calls `logger_flush`: `(*fp)(x)`");
    expect(stepSentence(step({ src: "N1", dst: "N2" }), label)).toBe("`main` calls `logger_flush`");
    expect(stepSentence(step({ kind: "return", src: "N3", dst: "N2", label: "-2" }), label)).toBe("`uart_send` returns `-2` to `logger_flush`");
    expect(stepSentence(step({ kind: "return", src: "N2", dst: "N1" }), label)).toBe("`logger_flush` returns to `main`");
    expect(stepSentence(step({ kind: "self", src: "N3", dst: "N3", label: "len > 64" }), label)).toBe("`uart_send`: `len > 64`");
    expect(stepSentence(step({ kind: "write", src: "N3", dst: "F1", label: "*err += 1" }), label))
      .toBe("`uart_send` writes `Uart::errors`: `*err += 1`");
    expect(stepSentence(step({ kind: "read", src: "F1", dst: "N4", label: "u->errors" }), label))
      .toBe("`uart_errors` reads `Uart::errors`: `u->errors`");
    expect(stepSentence(step({ kind: "fold", src: "N1", dst: "N3", folded: 3 }), label)).toBe("… 3 calls, `main` to `uart_send`");
    expect(stepSentence(step({ kind: "self", src: "N3", dst: "N3", label: "a `b` c" }), label)).toBe("`uart_send`: `a 'b' c`");
  });

  it("links a step to the story tab it comes from; a step of the code between them names its function", () => {
    expect(stepRef(step({ ref: "path", story: "S1", flow: "FL1", flow_n: 1 }), label))
      .toEqual({ text: "call path of S1 flow 1", link: { story: "S1", sec: "paths", flow: null } });
    expect(stepRef(step({ ref: "path", story: "S5" }), label).text).toBe("call path of S5");
    expect(stepRef(step({ ref: "change", story: "S1" }), label))
      .toEqual({ text: "S1 · the change", link: { story: "S1", sec: "code", flow: null } });
    expect(stepRef(step({ ref: "flow", story: "S1", flow: "FL3", flow_n: 2 }), label))
      .toEqual({ text: "S1 flow 2", link: { story: "S1", sec: null, flow: 2 } });
    expect(stepRef(step({ kind: "return", src: "N2", dst: "N1" }), label)).toEqual({ text: "`logger_flush`, unchanged", link: null });
    expect(stepRef(step({ kind: "read", src: "F1", dst: "N4" }), label).text).toBe("`uart_errors`, unchanged");
    expect(stepRef(step({ src: "N3", dst: "N2", status: "changed" }), label).text).toBe("`uart_send`, changed");
    expect(stepRef(step({ kind: "fold", src: "N1", dst: "N3", folded: 2 }), label)).toEqual({ text: "unchanged", link: null });
  });
});

describe("the drawing's layout (§4.4)", () => {
  const loop = "for (i = 0; i < len; i++)";
  const w = walk({ parts: ["N1", "N2", "N3"], steps: [
    step({ src: "N1", dst: "N2", label: "logger_flush(&g_log)" }),
    step({ kind: "self", src: "N3", dst: "N3", label: "len > 64", status: "new", loop }),
    step({ kind: "write", src: "N3", dst: "F1", label: "*err += 1", status: "new", loop }),
    step({ kind: "return", src: "N3", dst: "N2", label: "-2", status: "new" }),
    step({ kind: "read", src: "F1", dst: "N4", label: "u->errors" }),
    step({ kind: "fold", src: "N1", dst: "N3", folded: 3 }),
    step({ src: "N2", dst: "N2", label: "flush_again()", status: "changed" })] });
  const lay = walkLayout(w, label, (n) => (n === "N1" ? "app" : n === "N4" ? null : "driver"));

  it("gives each function a column, left to right, and one a step names that the parts miss a column at the end", () => {
    expect(lay.cols.map((c) => [c.label, c.component, c.x])).toEqual([
      ["main", "app", 143], ["logger_flush", "driver", 333], ["uart_send", "driver", 523], ["uart_errors", "", 713]]);
    expect(lay.width).toBe(LEFT + 4 * COL + COL / 2);
    expect(lay.height).toBe(TOP + 7 * ROW + FRAME + PAD);                              // one frame's label takes a band of its own
  });

  it("draws calls solid, returns dashed and folds dotted, and a step inside one function as a loop on its column", () => {
    expect(lay.rows.map((r) => [r.n, r.x1, r.x2, r.loop, r.line, r.status])).toEqual([
      [1, 143, 333, false, "solid", "same"], [2, 523, 523, true, "solid", "new"], [3, 523, 523, true, "solid", "new"],
      [4, 523, 333, false, "dashed", "new"], [5, 713, 713, true, "solid", "same"], [6, 143, 523, false, "dotted", "same"],
      [7, 333, 333, true, "solid", "changed"]]);
    expect(lay.rows.map((r) => r.y)).toEqual([74, 128, 164, 200, 236, 272, 308]);
    expect(lay.rows.map((r) => r.text)).toEqual(["logger_flush(&g_log)", "len > 64", "*err += 1", "-2", "u->errors", "… 3 calls",
                                                 "flush_again()"]);
  });

  it("frames the steps inside one loop of the code, and cuts what does not fit, keeping the whole for its title", () => {
    expect(lay.frames.map((f) => [f.x1, f.x2, f.y1, f.y2, f.full])).toEqual([[438, 608, 90, 176, loop]]);
    expect(lay.frames[0].text).toBe("loop · for (i = 0; i…");
    const long = walkLayout(walk({ parts: ["N1", "N2"], steps: [step({ src: "N1", dst: "N2", label: "x".repeat(80) })] }), label, () => null);
    expect(long.rows[0].text).toHaveLength(Math.floor((COL - 16) / CH));
    expect(long.rows[0].text.endsWith("…")).toBe(true);
    expect(long.rows[0].full).toBe("x".repeat(80));
    expect(long.frames).toEqual([]);
  });
});
