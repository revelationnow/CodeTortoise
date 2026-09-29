import { describe, expect, it } from "vitest";
import type { Impact } from "../api";
import { blastRings, flowElements } from "./graph";

const impact: Impact = {
  nodes: {
    N1: { id: "N1", key: "a", kind: "function", label: "a", file: null, line: null, status: "changed", layer: 1, confidence: "precise" },
    N2: { id: "N2", key: "b", kind: "function", label: "b", file: null, line: null, status: "unchanged", layer: 0, confidence: "precise" },
    N3: { id: "N3", key: "c", kind: "function", label: "c", file: null, line: null, status: "unchanged", layer: 0, confidence: "heuristic" },
    N4: { id: "N4", key: "field:f", kind: "field", label: "S::f", file: null, line: null, status: "unchanged", layer: null, confidence: "precise" },
  },
  edges: [
    { id: "E1", src: "N1", dst: "N2", kind: "call", status: "unchanged", confidence: "precise", file: null, line: null },
    { id: "E2", src: "N1", dst: "N3", kind: "call", status: "added", confidence: "precise", file: null, line: null },
    { id: "E3", src: "N1", dst: "N4", kind: "writes", status: "added", confidence: "precise", file: null, line: null },
  ],
  changed: ["N1"],
  flows: [{ root: "N1", nodes: ["N1", "N2", "N3"], edges: ["E1", "E2"] }],
  blast: [
    { node: "N2", hop: 1, score: 1, via: "call", path: ["N2", "N1"] },
    { node: "N3", hop: 1, score: 2, via: "data", path: ["N3", "N1"] },
  ],
  fanout: [],
};

describe("flowElements", () => {
  it("diff mode keeps everything with status classes", () => {
    const els = flowElements(impact, ["N1"], "diff", false);
    expect(els.map((e) => e.data.id)).toEqual(["N1", "N2", "N3", "E1", "E2"]);
    expect(els.find((e) => e.data.id === "E2")!.classes).toContain("st-added");
    expect(els.find((e) => e.data.id === "N3")!.classes).toContain("heuristic");
  });

  it("before mode drops added edges and orphaned nodes", () => {
    const els = flowElements(impact, ["N1"], "before", false);
    expect(els.map((e) => e.data.id)).toEqual(["N1", "N2", "E1"]);
  });

  it("data edges are optional", () => {
    const els = flowElements(impact, ["N1"], "after", true);
    expect(els.map((e) => e.data.id)).toContain("E3");
    expect(els.find((e) => e.data.id === "N4")!.classes).toContain("field");
  });
});

describe("blastRings", () => {
  it("groups by hop, highest score first", () => {
    expect([...blastRings(impact).get(1)!.map((x) => x.id)]).toEqual(["N3", "N2"]);
  });
});
