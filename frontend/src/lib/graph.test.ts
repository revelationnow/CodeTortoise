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

describe("flowElements at scale", () => {
  const many: Impact = {
    nodes: {
      R: { id: "R", key: "r", kind: "function", label: "root", file: "/w/src/a.c", line: 1, status: "changed", layer: 1, confidence: "precise" },
      ...Object.fromEntries(Array.from({ length: 9 }, (_, i) => [`C${i}`, {
        id: `C${i}`, key: `c${i}`, kind: "function" as const, label: `caller${i}`,
        file: i < 3 ? `/w/tests/t${i}.c` : `/w/src/c${i}.c`, line: 1, status: "unchanged" as const, layer: 2, confidence: "precise" as const,
      }])),
    },
    edges: Array.from({ length: 9 }, (_, i) => ({
      id: `E${i}`, src: `C${i}`, dst: "R", kind: "call" as const, status: "unchanged" as const, confidence: "precise" as const, file: null, line: null,
    })),
    changed: ["R"],
    flows: [{ root: "R", nodes: ["R", ...Array.from({ length: 9 }, (_, i) => `C${i}`)], edges: Array.from({ length: 9 }, (_, i) => `E${i}`) }],
    blast: [],
    fanout: [],
  };

  it("hides test code when asked", () => {
    const ids = flowElements(many, ["R"], "diff", false, { hideTests: true }).map((e) => e.data.id);
    expect(ids).not.toContain("C0");
    expect(ids).toContain("C3");
  });

  it("collapses callers beyond the cap into one summary node", () => {
    const els = flowElements(many, ["R"], "diff", false, { maxCallers: 4 });
    const callers = els.filter((e) => String(e.data.id).startsWith("C"));
    expect(callers).toHaveLength(4);
    const more = els.find((e) => e.data.id === "more:R")!;
    expect(more.data.label).toBe("+5 more callers");
    expect(els.some((e) => e.data.source === "more:R" && e.data.target === "R")).toBe(true);
  });
});

describe("flowElements depth and callee caps", () => {
  const node = (id: string, status: "changed" | "unchanged" = "unchanged") =>
    ({ id, key: id, kind: "function" as const, label: id, file: `/w/src/${id}.c`, line: 1, status, layer: 1, confidence: "precise" as const });
  const edge = (id: string, src: string, dst: string) =>
    ({ id, src, dst, kind: "call" as const, status: "unchanged" as const, confidence: "precise" as const, file: null, line: null });
  // R -> A -> B -> C (chain) and R -> L0..L4 (fan-out)
  const im: Impact = {
    nodes: Object.fromEntries(["R", "A", "B", "C", "L0", "L1", "L2", "L3", "L4"].map((n) => [n, node(n, n === "R" ? "changed" : "unchanged")])),
    edges: [edge("e1", "R", "A"), edge("e2", "A", "B"), edge("e3", "B", "C"),
      ...[0, 1, 2, 3, 4].map((i) => edge(`f${i}`, "R", `L${i}`))],
    changed: ["R"],
    flows: [{ root: "R", nodes: ["R", "A", "B", "C", "L0", "L1", "L2", "L3", "L4"], edges: ["e1", "e2", "e3", "f0", "f1", "f2", "f3", "f4"] }],
    blast: [], fanout: [],
  };

  it("limits distance from the roots", () => {
    const ids = flowElements(im, ["R"], "diff", false, { depth: 2 }).map((e) => e.data.id);
    expect(ids).toContain("B");
    expect(ids).not.toContain("C");
  });

  it("collapses callees beyond the cap", () => {
    const els = flowElements(im, ["R"], "diff", false, { maxCallees: 3 });
    expect(els.filter((e) => String(e.data.id).startsWith("L"))).toHaveLength(2); // A takes one of the 3 slots
    expect(els.find((e) => e.data.id === "more-out:R")!.data.label).toBe("+3 more callees");
  });
});
