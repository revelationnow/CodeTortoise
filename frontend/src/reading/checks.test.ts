import { describe, expect, it } from "vitest";
import { byThread, KIND_LABEL, letter, markLine, openCount, placeOf, splitChecks } from "./checks";
import type { Check, Mark, Reading, Thread } from "./types";

const check = (key: string, extra: Partial<Check> = {}): Check => ({
  key, kind: "caller", story: "S1", thread: "T1", path: "svc/flush.c", depot: "//d/svc/flush.c", line: 3, function: "flush",
  node: "N3", text: "`flush` calls `send` and was not updated for its new signature", source_line: "b = 0;", finding: null,
  cites: [], also: [], ...extra,
});
const mark = (key: string, changed = false): Mark => ({ key, user: "ana", at: "2026-10-07T10:00:00+00:00", source_line: "b = 0;", changed });
const thread = (id: string, name: string): Thread => ({ id, name, purpose: "", text_source: "template", stories: [], cls: [], open_checks: 0 });
const reading = (checks: Check[], threads: Thread[]): Reading => ({
  whole: "", whole_source: "template", threads, connections: [], order: [], reasons: {}, checks, cleared: [], build_impact: [],
  coverage: [], headline: { text: "No hazards found", tone: "none", rules_only: false }, rules_only: false, tests: null, marks: {},
});

describe("To check", () => {
  it("names every kind the way the reviewer reads it", () => {
    expect(KIND_LABEL.caller).toBe("Caller not updated");
    expect(KIND_LABEL.result).toBe("Result handled the old way");
    expect(KIND_LABEL.reader).toBe("Unchanged reader");
    expect(KIND_LABEL.ask).toBe("Ask the author");
  });

  it("puts open rows first and marked ones after, a mark on a changed line counting as open", () => {
    const rows = [check("a"), check("b"), check("c")];
    const { open, marked } = splitChecks(rows, { a: mark("a"), c: mark("c", true) });
    expect(open.map((k) => k.key)).toEqual(["b", "c"]);
    expect(marked.map((k) => k.key)).toEqual(["a"]);
  });

  it("counts open checks without ever showing an empty count", () => {
    expect(openCount(5, 5, false)).toBe("5 open");
    expect(openCount(3, 5, true)).toBe("3 of 5 open");
    expect(openCount(0, 2, true)).toBe("all 2 looked at");
    expect(openCount(0, 0, false)).toBe("");
  });

  it("groups checks by thread in reading order, checks with no thread last under Across the change", () => {
    const r = reading([check("x", { thread: null, story: null }), check("b", { thread: "T2" }), check("a")],
                      [thread("T1", "`send` in drv"), thread("T2", "`log` in svc")]);
    expect(byThread(r).map((g) => [g.label, g.checks.map((k) => k.key)])).toEqual([
      ["A · `send` in drv", ["a"]], ["B · `log` in svc", ["b"]], ["Across the change", ["x"]]]);
  });

  it("leaves out threads with nothing to check", () => {
    const r = reading([check("a")], [thread("T1", "one"), thread("T2", "two")]);
    expect(byThread(r).map((g) => g.label)).toEqual(["A · one"]);
  });

  it("letters threads A to Z, then by id", () => {
    expect([letter(0), letter(25), letter(26, "T27")]).toEqual(["A", "Z", "T27"]);
  });

  it("says where a check is, workspace-relative", () => {
    expect(placeOf(check("a"))).toBe("svc/flush.c:3 in `flush`");
    expect(placeOf(check("a", { line: null, function: null }))).toBe("svc/flush.c");
    expect(placeOf(check("a", { path: "", line: null, function: null }))).toBe("");
  });

  it("says who marked a check and when, or that its line changed since", () => {
    const now = Date.parse("2026-10-07T12:00:00+00:00");
    expect(markLine(mark("a"), now)).toBe("Looks fine · ana · 2h ago");
    expect(markLine(mark("a", true), now)).toBe("Changed since marked by ana");
  });
});
