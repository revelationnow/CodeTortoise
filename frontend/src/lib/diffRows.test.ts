import { describe, expect, it } from "vitest";
import { diffRows } from "./diffRows";

describe("diffRows", () => {
  it("numbers old and new lines and marks changes", () => {
    const rows = diffRows("a\nb\nc\n", "a\nB\nc\nd\n");
    expect(rows.map((r) => [r.kind, r.oldNo, r.newNo, r.text])).toEqual([
      ["ctx", 1, 1, "a"], ["del", 2, null, "b"], ["add", null, 2, "B"], ["ctx", 3, 3, "c"], ["add", null, 4, "d"],
    ]);
  });

  it("collapses long unchanged runs", () => {
    const before = Array.from({ length: 20 }, (_, i) => `l${i}`).join("\n") + "\n";
    const after = before.replace("l10\n", "L10\n");
    const rows = diffRows(before, after, 2);
    expect(rows[0]).toEqual({ kind: "gap", oldNo: null, newNo: null, text: "8 unchanged line(s)" });
    expect(rows.filter((r) => r.kind !== "gap").map((r) => r.text)).toEqual(["l8", "l9", "l10", "L10", "l11", "l12"]);
    expect(rows[rows.length - 1].text).toBe("7 unchanged line(s)");
  });

  it("handles added and deleted files", () => {
    expect(diffRows("", "x\n").map((r) => r.kind)).toEqual(["add"]);
    expect(diffRows("x\n", "").map((r) => r.kind)).toEqual(["del"]);
  });
});
