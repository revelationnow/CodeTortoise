import { describe, expect, it } from "vitest";
import type { BoardFlow } from "../board/types";
import { changedOf, fieldOf, flowGroups, flowPlaces, groupCauses, groupLine, groupShort, groupTitle, openFlows, openKeys, placesOf,
         rowSentence, someNames, tail } from "./flowGroups";
import type { Cause, Check, CheckKind, Mark } from "./types";

const NAMES: Record<string, string> = {
  N1: "main", N2: "logger_flush", N3: "uart_send", N4: "Uart::errors", N5: "uart_errors", N6: "uart_init", N7: "hal_write",
  N8: "logger_write", N9: "uart_stats", N10: "Uart::errors",                  // N10: another field, named like N4
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
const reads2 = flow("f6", "state", ["N1", "N3", "N10", "N9"], "N3", "main → uart_send → Uart::errors → uart_stats",
                    "uart_stats sees a new writer of Uart::errors");                // a field N10 named like N4 (two structs, one member name)

function check(key: string, kind: CheckKind, node: string, related: string | null | undefined, field: string | null = null): Check {
  const k: Check = { key, kind, story: "S1", thread: "T1", path: "a.c", depot: null, line: 1, function: label(node), node,
                     text: key, source_line: "", finding: null, cites: [], cause: `c-${key}`, field };
  if (related !== undefined) k.related = related;
  return k;
}
/** The same checks as a reading stored before `related` has them (Review Focus 1): `related` absent, or null as the server
 * sends it on a row with no changed function behind it; the page reads the two alike. */
const stored = (ks: Check[], missing: null | undefined = undefined) =>
  ks.map((k) => check(k.key, k.kind, k.node!, missing, k.field ?? null));
const MISSING = [["related absent", undefined], ["related null", null]] as const;
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

  /** `count` flows of the three shapes, spread over several fields, writers and changed functions. */
  function story(count: number): BoardFlow[] {
    return Array.from({ length: count }, (_, i) => {
      const id = `g${i}`, writer = `W${i % 4}`, field = `F${i % 5}`, fn = `C${i % 5}`, reader = `R${i}`;
      return i % 3 === 0 ? flow(id, "state", ["N1", writer, field, reader], writer, id, id)       // by its field
        : i % 3 === 1 ? flow(id, "state", ["N1", writer, reader], writer, id, id)                 // by its writer: no field before the reader
          : flow(id, "contract", ["N1", reader, fn], fn, id, id);                                 // by its changed function
    });
  }

  it("holds each of 30 or more flows once, with its own number, in the story's order within its group and groups in the order of their first", () => {
    const flows = story(36), groups = flowGroups(flows);
    expect(new Set(groups.map((g) => g.kind))).toEqual(new Set(["field", "writer", "function"]));
    expect(groups.length).toBeGreaterThan(10);
    const numbers = groups.flatMap((g) => g.rows.map((r) => r.n));
    expect(numbers.slice().sort((a, b) => a - b)).toEqual(flows.map((_, i) => i + 1));            // none lost, none twice
    const increasing = (ns: number[]) => ns.every((n, i) => i === 0 || n > ns[i - 1]);
    for (const g of groups) {
      expect(g.rows.every((r) => r.flow === flows[r.n - 1]), g.key).toBe(true);
      expect(increasing(g.rows.map((r) => r.n)), g.key).toBe(true);
    }
    expect(increasing(groups.map((g) => g.rows[0].n))).toBe(true);
    expect(new Set(groups.map((g) => g.key)).size).toBe(groups.length);
  });

  it("makes two groups, with their own keys, of two nodes that share a label", () => {
    const both = flowGroups([reads, reads2]);
    expect(both.map((g) => [g.key, g.node, label(g.node)])).toEqual([["field:N4", "N4", "Uart::errors"], ["field:N10", "N10", "Uart::errors"]]);
    expect(both.map((g) => groupTitle(g, label))).toEqual(Array(2).fill("`Uart::errors` gets a new writer: `uart_send`"));
  });
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

  it("writes a name with a backtick in it with a quote instead, or `Ticks` would flip code and text for the rest of the line", () => {
    expect(someNames(["a`b"])).toBe("`a'b`");
    const lab = (n: string) => (n === "N3" ? "uart`send" : label(n));
    expect(groupTitle(fn, lab)).toBe("`uart'send` returns new values");
    expect(groupTitle(field, lab)).toBe("`Uart::errors` gets a new writer: `uart'send`");
    expect(groupShort(writer, lab)).toBe("`uart'send`'s writes");
    expect(rowSentence(reads, lab)).toBe("`uart_errors` sees a new writer of `Uart::errors` · via `uart'send`");
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

  it.each(MISSING)("are none on a reading stored before `related` (%s), or for a flow without a change (Review Focus 1)", (_, missing) => {
    expect([ignored, reads, blind].map((f) => flowPlaces(f, stored(checks, missing), none, label))).toEqual([[], [], []]);
    expect(flowPlaces({ ...ignored, cause: null }, checks, none, label)).toEqual([]);
  });

  it("keep a flow open while any is unmarked or its line changed since", () => {
    const places = placesOf([ignored, reads], checks, none, label), [g] = flowGroups([ignored]);
    expect(openKeys(places.get("f1")!, { "result|flush": mark("result|flush") })).toEqual(["caller|flush"]);
    expect(openFlows(g, places, { "result|flush": mark("result|flush"), "caller|flush": mark("caller|flush") })).toBe(0);
    expect(openFlows(g, places, { "result|flush": mark("result|flush"), "caller|flush": mark("caller|flush", true) })).toBe(1);
  });
});

describe("placesOf", () => {
  const twin = flow("f7", "contract", ["N1", "N8", "N2", "N3"], "N3", "main → logger_write → logger_flush → uart_send ⟶ -2 ignored",
                    "logger_flush ignores -2, again");                                // shares f1's change and its landing
  const causeless = { ...ignored, id: "f8", cause: null };
  const flows = [ignored, twin, reads, blind, reads2, unhandled, sig, causeless];
  const checks = [
    check("result|flush", "result", "N2", "N3"), check("caller|flush", "caller", "N2", "N3"), check("confirm|flush", "confirm", "N2", "N3"),
    check("reader|errors", "reader", "N5", "N3", "Uart::errors"), check("reader|state", "reader", "N5", "N3", "Uart::state"),
    check("reader|stats", "reader", "N9", "N3", "Uart::errors"), check("target|write", "target", "N8", "N3"),
    check("result|init", "result", "N6", "N7"), check("caller|loose", "caller", "N2", null), check("untested|s1", "untested", "N3", null),
    { ...check("caller|nowhere", "caller", "N2", "N3"), node: null },
  ];
  /** `placesOf` as it was before the index: every flow against every check. */
  const scan = (list: Check[], hidden: ReadonlySet<CheckKind>) => new Map(flows.map((f) => [f.id, flowPlaces(f, list, hidden, label)]));
  const keys = (m: Map<string, Check[]>) => [...m].map(([id, ks]) => [id, ks.map((k) => k.key)]);

  it("finds what the old scan did: a shared change and landing give two flows the same places, a hidden kind none", () => {
    expect(keys(placesOf(flows, checks, none, label))).toEqual([
      ["f1", ["result|flush", "caller|flush"]], ["f7", ["result|flush", "caller|flush"]], ["f2", ["reader|errors"]],
      ["f4", ["reader|errors", "reader|state"]], ["f6", ["reader|stats"]], ["f3", ["target|write"]], ["f5", ["result|init"]], ["f8", []]]);
    const kinds: CheckKind[] = ["hazard", "confirm", "caller", "result", "reader", "target", "untested", "unanalysed", "ask"];
    for (const hidden of [none, new Set<CheckKind>(["result"]), new Set<CheckKind>(["reader", "caller"]), new Set(kinds)])
      expect(placesOf(flows, checks, hidden, label), [...hidden].join()).toEqual(scan(checks, hidden));
    expect(keys(placesOf(flows, checks, new Set<CheckKind>(["result"]), label))[0]).toEqual(["f1", ["caller|flush"]]);
  });

  it("reads each check a few times, not once for every flow", () => {
    const side = 20, many: BoardFlow[] = [], list: Check[] = [];
    let reads = 0;
    for (let i = 0; i < side; i++) {
      for (let j = 0; j < side; j++) {                                              // a flow and its check at every (change, landing) pair
        many.push(flow(`m${i}-${j}`, "contract", ["N1", `P${j}`, `C${i}`], `C${i}`, "", ""));
        const k = check(`k${i}-${j}`, "caller", `P${j}`, `C${i}`), related = k.related;
        Object.defineProperty(k, "related", { get: () => (reads++, related), enumerable: true });
        list.push(k);
      }
    }
    const found = placesOf(many, list, none, label);
    expect(many.every((f, n) => found.get(f.id)!.length === 1 && found.get(f.id)![0] === list[n])).toBe(true);
    expect(reads).toBeLessThan(10 * (many.length + list.length));                    // a scan of every check for every flow reads 2 × 400 × 400
  });

  it("are none for a flow on a reading stored before `related`, or where every `related` is null (consumers count on it)", () => {
    for (const missing of [undefined, null]) {
      const found = placesOf(flows, stored(checks, missing), none, label);
      expect([...found.values()].flat()).toEqual([]);
      expect([...found.keys()]).toEqual(flows.map((f) => f.id));                     // each flow still has its (empty) entry
    }
  });

  it("makes a writer group of a state flow without a cause and finds it no places, whatever is raised at its landing", () => {
    const raised = [check("reader|errors", "reader", "N5", "N3", "Uart::errors"), check("reader|null", "reader", "N5", null, "Uart::errors"),
                    check("reader|absent", "reader", "N5", undefined, "Uart::errors")];
    for (const missing of [null, undefined]) {
      const orphan = { ...reads, id: "f9", cause: missing };
      expect(flowGroups([orphan]).map((g) => [g.kind, g.rows.length])).toEqual([["writer", 1]]);
      expect(placesOf([orphan], raised, none, label).get("f9")).toEqual([]);
    }
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

  it.each(MISSING)("falls back to a function group of the cause's flows on a reading stored before `related` (%s; Review Focus 1)", (_, missing) => {
    const { byGroup, rest } = groupCauses(groups, [...causes, cause("lost", "caller", [], [])], stored(checks, missing), label);
    expect(ids(byGroup)).toEqual([["function:N3", ["result", "hazard"]], ["field:N4", ["reader"]], ["function:N7", ["caller"]]]);
    expect(rest.map((c) => c.id)).toEqual(["target", "untested", "state", "lost"]);
  });

  describe("a reading stored before `related`: a contract cause goes to a function, never to a field or a writer (owner decision 4)", () => {
    // groups: field:N4 [f2], writer:N3 [f4], function:N3 [f1], function:N7 [f5]
    const mixed = flowGroups([reads, blind, ignored, sig]);
    /** Where one cause of `kind` with `flows` and one check lands: its group's key, or "end" for the end line. `related`
     * undefined leaves it off the check, as a reading stored before it has the check. */
    const lands = (kind: CheckKind, flows: string[], related: string | null | undefined) => {
      const k = check("k", kind, "N2", related);
      const { byGroup, rest } = groupCauses(mixed, [cause("c", kind, ["k"], flows)], [k], label);
      return rest.length ? "end" : [...byGroup.keys()].join();
    };
    const CONTRACT: CheckKind[] = ["caller", "result", "target", "unanalysed"];

    it.each(CONTRACT)("a %s cause takes the first function group among its flows, in the order of its flows", (kind) => {
      for (const missing of [undefined, null]) {
        const is = (flows: string[], group: string) => expect(lands(kind, flows, missing), `${flows.join()} with related ${missing}`).toBe(group);
        is(["f2", "f1"], "function:N3");                                // the field group of f2 comes first in the list, but is no function
        is(["f4", "f2", "f5", "f1"], "function:N7");
        is(["f5", "f1"], "function:N7");                                // the order of its flows, not of the groups
        is(["f1", "f5"], "function:N3");
        is(["f99", "f1"], "function:N3");                               // a flow no group holds is passed over
      }
    });

    it.each(CONTRACT)("a %s cause none of whose flows is in a function group goes to the end line", (kind) => {
      for (const missing of [undefined, null])
        for (const flows of [["f2"], ["f4"], ["f2", "f4"], ["f99"], []]) expect(lands(kind, flows, missing), `${flows.join()} with related ${missing}`).toBe("end");
    });

    it("a cause with `related` set goes by `related`, as before, whatever its flows say", () => {
      expect(lands("caller", ["f2", "f1"], "N7")).toBe("function:N7");
      expect(lands("caller", ["f5"], "N3")).toBe("function:N3");
      expect(lands("caller", ["f1"], "N6")).toBe("end");                // a function with no flow in this story has no group: the end line, not f1's
    });
  });

  it("keeps two fields that share a label apart: a reader cause goes to the field its checks land at", () => {
    const twins = flowGroups([reads, reads2]);                          // field:N4 read by N5, and field:N10 read by N9: both `Uart::errors`
    const rows = [check("reader|errors", "reader", "N5", "N3", "Uart::errors"), check("reader|stats", "reader", "N9", "N3", "Uart::errors"),
                  check("reader|far", "reader", "N6", "N3", "Uart::errors")];
    const cs = [cause("at-n10", "reader", ["reader|stats"], ["f6"]), cause("at-n4", "reader", ["reader|errors"], ["f2"]),
                cause("both", "reader", ["reader|errors", "reader|stats"], ["f2", "f6"]),
                cause("neither", "reader", ["reader|far"], [])];
    const { byGroup, rest } = groupCauses(twins, cs, rows, label);
    expect(ids(byGroup)).toEqual([["field:N10", ["at-n10"]], ["field:N4", ["at-n4", "both", "neither"]]]);
    expect(rest).toEqual([]);                                           // landing nowhere: the first of the groups the label names, as before
  });

  it("puts every shown cause in exactly one place, even one two groups match or none does (consumers count on it)", () => {
    const twins = flowGroups([ignored, reads, reads2, unhandled, blind, sig]);
    const rows = [check("r1", "reader", "N5", "N3", "Uart::errors"), check("r2", "reader", "N9", "N3", "Uart::errors"),
                  check("r3", "reader", "N5", "N3", "nothing here"), check("res", "result", "N2", "N3"), check("call", "caller", "N6", "N7"),
                  check("t", "target", "N9", "N9"), check("u", "untested", "N3", null)];
    const cs = [cause("both-fields", "reader", ["r1", "r2"], ["f2", "f6"]), cause("no-field", "reader", ["r3"], ["f2"]),
                cause("no-places", "reader", [], ["f2"]), cause("result", "result", ["res"], ["f1", "f2"]), cause("caller", "caller", ["call"], ["f5"]),
                cause("target", "target", ["t"], []), cause("untested", "untested", ["u"], ["f4"]),
                cause("two-flows-two-groups", "hazard", [], ["f1", "f2"], "F2"), cause("hazard-nobody", "hazard", [], ["f1"], "F99"),
                cause("hazard-no-finding", "hazard", [], ["f1"]), cause("confirm", "confirm", [], ["f2"], "F2")];
    for (const checks of [rows, stored(rows), stored(rows, null)]) {
      const { byGroup, rest } = groupCauses(twins, cs, checks, label);
      const placed = [...[...byGroup.values()].flat(), ...rest].map((c) => c.id);
      expect(placed.slice().sort(), "each exactly once").toEqual(cs.map((c) => c.id).sort());
      for (const list of [...byGroup.values(), rest]) {                // and each list keeps the order the causes came in
        const at = list.map((c) => cs.indexOf(c));
        expect(at).toEqual(at.slice().sort((a, b) => a - b));
      }
      expect([...byGroup.keys()].every((key) => twins.some((g) => g.key === key))).toBe(true);
    }
  });
});
