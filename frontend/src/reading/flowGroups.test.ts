import { describe, expect, it } from "vitest";
import type { BoardFlow } from "../board/types";
import { changedOf, fieldOf, flowGroups, flowPlaces, groupCauses, groupLine, groupShort, groupTitle, openFlows, openKeys, placesOf,
         rowSentence, someNames, tail } from "./flowGroups";
import type { Cause, Check, CheckKind, Mark } from "./types";

const NAMES: Record<string, string> = {
  N1: "main", N2: "logger_flush", N3: "uart_send", N4: "Uart::errors", N5: "uart_errors", N6: "uart_init", N7: "hal_write",
  N8: "logger_write", N9: "uart_stats",
};
const label = (n: string) => NAMES[n] ?? "a function";

/** A flow as `board.py` `build_flows` makes it: a contract path ends at its change, a state path at its reader. */
function flow(id: string, tag: "state" | "contract", path: string[], cause: string | null | undefined, text: string, title: string,
              findings: string[] = []): BoardFlow {
  return { id, path, tag, lands: tag === "state" ? path[path.length - 1] : path[path.length - 2], fx_at: null, severity: "medium",
           findings, text, title, what: "", effect: "", check: "", what_source: "template", cause };
}
const ignored = flow("f1", "contract", ["N1", "N2", "N3"], "N3", "main → logger_flush → uart_send ⟶ -2 ignored", "logger_flush ignores -2", ["F2"]);
const reads = flow("f2", "state", ["N1", "N3", "N4", "N5"], "N3", "main → uart_send → Uart::errors → uart_errors",
                   "uart_errors sees a new writer of Uart::errors");
const unhandled = flow("f3", "contract", ["N1", "N8", "N3"], "N3", "main → logger_write → uart_send ⟶ -2 unhandled",
                       "logger_write doesn't handle -2");
const blind = flow("f4", "state", ["N1", "N3", "N5"], "N3", "main → uart_send → uart_errors", "uart_errors sees a new writer of the field");
const sig = flow("f5", "contract", ["N1", "N6", "N7"], "N7", "main → uart_init → hal_write ⟶ signature changed",
                 "uart_init calls hal_write (signature changed)");

function check(key: string, kind: CheckKind, node: string, related: string | null | undefined, field: string | null = null): Check {
  const k: Check = { key, kind, story: "S1", thread: "T1", path: "a.c", depot: null, line: 1, function: label(node), node,
                     text: key, source_line: "", finding: null, cites: [], cause: `c-${key}`, field };
  if (related !== undefined) k.related = related;
  return k;
}
/** The same checks as a reading stored before `related` has them (Review Focus 1). */
const stored = (ks: Check[]) => ks.map((k) => check(k.key, k.kind, k.node!, undefined, k.field ?? null));
const cause = (id: string, kind: CheckKind, places: string[], flows: string[] = [], finding: string | null = null): Cause =>
  ({ id, kind, thread: "T1", story: "S1", text: id, places, flows, finding, change: null });
const mark = (key: string, changed = false): Mark => ({ key, user: "ana", at: "", source_line: "", changed });
const none = new Set<CheckKind>();

describe("a flow's field and change", () => {
  it("finds a state flow's field before its reader, never its writer, and none on a contract flow", () => {
    expect(fieldOf(reads)).toBe("N4");
    expect(fieldOf(blind)).toBeNull();                        // the node before the reader is the writer itself
    expect(fieldOf(ignored)).toBeNull();
    expect(fieldOf({ ...reads, path: ["N5"] })).toBeNull();
    expect(fieldOf({ ...reads, cause: null })).toBeNull();    // without its writer the field cannot be told apart
  });

  it("takes a flow's change from its cause, else from the end of a contract path", () => {
    expect(changedOf(reads)).toBe("N3");
    expect(changedOf({ ...sig, cause: undefined })).toBe("N7");
  });
});

describe("flowGroups", () => {
  it("groups state flows by field (else writer) and contract flows by changed function, in the order of their first flow", () => {
    const g = flowGroups([ignored, reads, unhandled, blind, sig]);
    expect(g.map((x) => [x.key, x.kind, x.node, x.rows.map((r) => r.n)])).toEqual([
      ["function:N3", "function", "N3", [1, 3]], ["field:N4", "field", "N4", [2]], ["writer:N3", "writer", "N3", [4]],
      ["function:N7", "function", "N7", [5]]]);
    expect(g[0].rows.map((r) => r.flow.id)).toEqual(["f1", "f3"]);
  });

  it("makes no group of no flows", () => expect(flowGroups([])).toEqual([]));
});

describe("a group's title, line and outline line", () => {
  const [fn, field, writer, hal] = flowGroups([ignored, reads, unhandled, blind, sig]);

  it("says what changed", () => {
    expect(groupTitle(fn, label)).toBe("`uart_send` returns new values");
    expect(groupTitle(field, label)).toBe("`Uart::errors` gets a new writer: `uart_send`");
    expect(groupTitle(writer, label)).toBe("New writes by `uart_send`");
    expect(groupTitle(hal, label)).toBe("`hal_write`'s signature changed");
    const [mixed] = flowGroups([sig, flow("f6", "contract", ["N1", "N8", "N7"], "N7", "main → logger_write → hal_write ⟶ -2 ignored",
                                          "logger_write ignores -2")]);
    expect(groupTitle(mixed, label)).toBe("`hal_write` changed");
  });

  it("names a field's writers once each, in order, the rest as a count", () => {
    const more: Record<string, string> = { W1: "stats_a1", W2: "stats_a2", W3: "stats_a3", W4: "stats_b1", W5: "stats_b2" };
    const lab = (n: string) => more[n] ?? label(n);
    const by = (id: string, w: string) => flow(id, "state", ["N1", w, "N4", "N5"], w, id, "");
    const [two] = flowGroups([by("a", "W4"), by("b", "W5"), by("c", "W4")]);
    expect(groupTitle(two, lab)).toBe("`Uart::errors` gets new writers: `stats_b1`, `stats_b2`");
    const [five] = flowGroups(["W1", "W2", "W3", "W4", "W5"].map((w) => by(w, w)));
    expect(groupTitle(five, lab)).toBe("`Uart::errors` gets new writers: `stats_a1`, `stats_a2`, `stats_a3` and 2 more");
  });

  it("says who reads or calls, how many flows, and how many are open only when some are", () => {
    expect(groupLine(fn, label, 1)).toBe("called by `logger_flush`, `logger_write` · 2 flows · 1 open");
    expect(groupLine(field, label, 0)).toBe("read by `uart_errors` · 1 flow");
    expect(groupLine(writer, label, 1)).toBe("read by `uart_errors` · 1 flow · 1 open");
    expect(someNames(["a", "b", "a", "c", "d", "e"])).toBe("`a`, `b`, `c` and 2 more");
    expect(someNames(["a"])).toBe("`a`");
  });

  it("names a group in the outline by its field, its writer's writes or its function", () => {
    expect([fn, field, writer].map((g) => groupShort(g, label))).toEqual(["`uart_send`", "`Uart::errors`", "`uart_send`'s writes"]);
  });

  it("reads a contract flow's ending after its last arrow", () => {
    expect(tail(sig.text)).toBe("signature changed");
    expect(tail("a → b")).toBe("");
  });
});

describe("rowSentence", () => {
  it("tells a state flow by reader, field and writer, a contract flow by its title with the landing in code style", () => {
    expect(rowSentence(reads, label)).toBe("`uart_errors` sees a new writer of `Uart::errors` · via `uart_send`");
    expect(rowSentence(blind, label)).toBe("`uart_errors` sees new writes by `uart_send`");
    expect(rowSentence(ignored, label)).toBe("`logger_flush` ignores -2");
    expect(rowSentence({ ...ignored, title: "something else" }, label)).toBe("something else");
  });
});

describe("a flow's places", () => {
  const checks = [
    check("result|flush", "result", "N2", "N3"), check("caller|flush", "caller", "N2", "N3"),
    check("reader|errors", "reader", "N5", "N3", "Uart::errors"), check("reader|state", "reader", "N5", "N3", "Uart::state"),
    check("confirm|flush", "confirm", "N2", "N3"), check("result|init", "result", "N6", "N7"),
  ];

  it("are the checks its change raised at its landing, of a kind it asks about", () => {
    expect(flowPlaces(ignored, checks, none, label).map((k) => k.key)).toEqual(["result|flush", "caller|flush"]);
    expect(flowPlaces(reads, checks, none, label).map((k) => k.key)).toEqual(["reader|errors"]);
    expect(flowPlaces(blind, checks, none, label).map((k) => k.key)).toEqual(["reader|errors", "reader|state"]);
    expect(flowPlaces(unhandled, checks, none, label)).toEqual([]);
  });

  it("leave hidden kinds out", () => {
    expect(flowPlaces(ignored, checks, new Set<CheckKind>(["result"]), label).map((k) => k.key)).toEqual(["caller|flush"]);
  });

  it("are none on a reading stored before checks named their change, or for a flow without one (Review Focus 1)", () => {
    expect([ignored, reads, blind].map((f) => flowPlaces(f, stored(checks), none, label))).toEqual([[], [], []]);
    expect(flowPlaces({ ...ignored, cause: null }, checks, none, label)).toEqual([]);
  });

  it("keep a flow open while any is unmarked or its line changed since", () => {
    const places = placesOf([ignored, reads], checks, none, label), [g] = flowGroups([ignored]);
    expect(openKeys(places.get("f1")!, { "result|flush": mark("result|flush") })).toEqual(["caller|flush"]);
    expect(openFlows(g, places, { "result|flush": mark("result|flush"), "caller|flush": mark("caller|flush") })).toBe(0);
    expect(openFlows(g, places, { "result|flush": mark("result|flush"), "caller|flush": mark("caller|flush", true) })).toBe(1);
  });
});

describe("groupCauses", () => {
  const groups = flowGroups([ignored, reads, unhandled, sig]);
  const checks = [
    check("result|flush", "result", "N2", "N3"), check("reader|errors", "reader", "N5", "N3", "Uart::errors"),
    check("caller|init", "caller", "N6", "N7"), check("target|stats", "target", "N9", "N9"), check("untested|s1", "untested", "N3", null),
    check("reader|state", "reader", "N5", "N3", "Uart::state"),
  ];
  const causes = [
    cause("result", "result", ["result|flush"], ["f1", "f2"]), cause("reader", "reader", ["reader|errors"], ["f1", "f2"]),
    cause("hazard", "hazard", [], ["f1"], "F2"), cause("caller", "caller", ["caller|init"], ["f5"]),
    cause("target", "target", ["target|stats"]), cause("untested", "untested", ["untested|s1"]),
    cause("state", "reader", ["reader|state"], ["f2"]),
  ];
  const ids = (m: Map<string, Cause[]>) => [...m].map(([k, cs]) => [k, cs.map((c) => c.id)]);

  it("puts a reader with its field, a caller's kinds with their function, a hazard with its finding's flow, the rest last", () => {
    const { byGroup, rest } = groupCauses(groups, causes, checks, label);
    expect(ids(byGroup)).toEqual([["function:N3", ["result", "hazard"]], ["field:N4", ["reader"]], ["function:N7", ["caller"]]]);
    expect(rest.map((c) => c.id)).toEqual(["target", "untested", "state"]);
  });

  it("falls back to the group holding a cause's first flow on a reading stored before `related` (Review Focus 1)", () => {
    const { byGroup, rest } = groupCauses(groups, [...causes, cause("lost", "caller", [], [])], stored(checks), label);
    expect(ids(byGroup)).toEqual([["function:N3", ["result", "hazard"]], ["field:N4", ["reader"]], ["function:N7", ["caller"]]]);
    expect(rest.map((c) => c.id)).toEqual(["target", "untested", "state", "lost"]);
  });
});
