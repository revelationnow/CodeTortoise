import { describe, expect, it } from "vitest";
import { driftSummary } from "./drift";

describe("drift summary", () => {
  it("separates warnings from expected newer files", () => {
    const d = [{ text: "a (base #3, workspace #4)", kind: "ahead", severity: "info" },
               { text: "b (base #7, workspace #5)", kind: "behind", severity: "warn" },
               { text: "c (base #2, workspace not synced)", kind: "missing", severity: "warn" },
               { text: "d (base #1, workspace #9)", kind: "ahead", severity: "info" }] as const;
    expect(driftSummary([...d])).toEqual({ warn: ["b (base #7, workspace #5)", "c (base #2, workspace not synced)"],
                                           info: ["a (base #3, workspace #4)", "d (base #1, workspace #9)"] });
  });

  it("treats drift stored before kinds as warnings", () => {
    expect(driftSummary([{ text: "x" }])).toEqual({ warn: ["x"], info: [] });
  });
});
