import { describe, expect, it } from "vitest";
import type { Finding } from "../api";
import { listFindings } from "./findings";

const f = (id: string, severity: Finding["severity"], state: Finding["state"] = "open") =>
  ({ id, severity, state, kind: "contract", title: id, nodes: [], evidence: [], summary: "", explanation: null,
     verify_steps: [], hypotheses: [], files: null }) as Finding;

describe("listFindings", () => {
  const all = [f("F10", "low"), f("F2", "high", "ack"), f("F1", "high"), f("F3", "info", "dismissed"), f("F4", "medium")];

  it("puts the worst first, then by id as a number", () => {
    expect(listFindings(all, null, null).map((x) => x.id)).toEqual(["F1", "F2", "F4", "F10", "F3"]);
  });

  it("filters by severity and by status", () => {
    expect(listFindings(all, "high", null).map((x) => x.id)).toEqual(["F1", "F2"]);
    expect(listFindings(all, null, "dismissed").map((x) => x.id)).toEqual(["F3"]);
    expect(listFindings(all, "high", "dismissed")).toEqual([]);
  });
});
