import { describe, expect, it } from "vitest";
import { KIND_LABEL, letter, markLine, placeOf, threadLabel } from "./checks";
import type { Check, Mark } from "./types";

const check = (key: string, extra: Partial<Check> = {}): Check => ({
  key, kind: "caller", story: "S1", thread: "T1", path: "svc/flush.c", depot: "//d/svc/flush.c", line: 3, function: "flush",
  node: "N3", text: "`flush` calls `send` and was not updated for its new signature", source_line: "b = 0;", finding: null,
  cites: [], ...extra,
});
const mark = (key: string, changed = false): Mark => ({ key, user: "ana", at: "2026-10-07T10:00:00+00:00", source_line: "b = 0;", changed });

describe("To check", () => {
  it("names every kind the way the reviewer reads it", () => {
    expect(KIND_LABEL.caller).toBe("Caller not updated");
    expect(KIND_LABEL.result).toBe("Result handled the old way");
    expect(KIND_LABEL.reader).toBe("Unchanged reader");
    expect(KIND_LABEL.ask).toBe("Ask the author");
  });

  it("letters threads A to Z, then by id", () => {
    expect([letter(0), letter(25), letter(26, "T27")]).toEqual(["A", "Z", "T27"]);
  });

  it("names a story's thread as the rail does, past Z too, and a story in no thread as Tests", () => {
    const threads = Array.from({ length: 28 }, (_, i) => ({ id: `T${i + 1}`, stories: [`S${i + 1}`] }));
    expect(["S1", "S26", "S27", "S99"].map((s) => threadLabel(threads, s))).toEqual(["Thread A", "Thread Z", "Thread T27", "Tests"]);
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
