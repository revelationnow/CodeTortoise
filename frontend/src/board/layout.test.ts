import { describe, expect, it } from "vitest";
import { centrePan, flowSets, layerRows, placeCards, worldNodes } from "./layout";
import type { Board, BoardFlow } from "./types";

const node = (id: string, layer: number | null, x: number) => ({
  id, key: id, label: id, kind: "function" as const, layer, path: null, local: null, range: null, change: null, x, warn: 0,
});
const board = {
  nodes: [node("A", 3, 0), node("B", 1, -220), node("C", 1, 220), node("D", null, 0)],
  edges: [], flows: [], impacts: [], layers: [{ level: 3, name: "app" }, { level: 1, name: "hal" }],
  about: { intent: "", intent_source: "template", why: [], cls: [], tree: [] }, hidden_nodes: 0,
} as Board;

describe("layout", () => {
  it("puts higher layers on top and unlayered nodes last", () => {
    expect([...layerRows(board)]).toEqual([[3, 0], [1, 1], [-1, 2]]);
    const w = worldNodes(board, { C: 500 });
    expect(w.get("A")).toEqual({ id: "A", x: 0, y: 105 });
    expect(w.get("C")).toEqual({ id: "C", x: 500, y: 315 });
    expect(w.get("D")!.y).toBe(525);
  });

  it("centres a set of nodes", () => {
    const w = worldNodes(board, {});
    expect(centrePan(["B", "C"], w, 1000, 600)).toEqual({ panX: 500, panY: 300 - 315 });
    expect(centrePan(["nope"], w, 1000, 600)).toBeNull();
  });

  it("marks the selected flow's nodes and call pairs", () => {
    const f = { path: ["A", "B", "C"] } as BoardFlow;
    const s = flowSets(f, false);
    expect([...s.onPath]).toEqual(["A", "B", "C"]);
    expect([...s.pairs]).toEqual(["A>B", "B>C"]);
    expect(flowSets(f, true).onPath.size).toBe(0);
  });

  it("places cards beside their node without overlap and inside the canvas", () => {
    const at = { x: 500, y: 300, v: 1, s: 1 };
    const rects = placeCards([{ id: "1", at, w: 300, h: 200, collapsed: false },
                              { id: "2", at, w: 300, h: 200, collapsed: false }], 1200, 800);
    const a = rects.get("1")!, b = rects.get("2")!;
    expect(a.x).toBe(600);                                     // right of the node, clear of it
    expect(b.x + b.w).toBeLessThanOrEqual(450);                // then left of it
    for (const r of [a, b]) expect(r.x >= 8 && r.y >= 8 && r.x + r.w <= 1192 && r.y + r.h <= 792).toBe(true);
  });

  it("keeps dragged offsets, scales by the lens and puts pills under the node", () => {
    const rects = placeCards([
      { id: "d", at: { x: 400, y: 300, v: 1, s: 0.4 }, w: 300, h: 200, collapsed: false, offset: { x: 10, y: 20 } },
      { id: "p", at: { x: 600, y: 300, v: 1, s: 1 }, w: 100, h: 30, collapsed: true },
    ], 1200, 800);
    const d = rects.get("d")!;
    expect([d.x, d.y, Math.round(d.w), Math.round(d.h), d.k]).toEqual([410, 320, 165, 110, 0.55]);
    expect(rects.get("p")).toEqual({ x: 550, y: 324, w: 100, h: 30, k: 1 });
  });
});
