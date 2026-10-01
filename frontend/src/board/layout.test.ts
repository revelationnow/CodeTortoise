import { describe, expect, it } from "vitest";
import { centrePan, flowSets, layerRows, placeCards, worldNodes } from "./layout";
import type { Board, BoardEdge, BoardFlow, BoardNode } from "./types";

const node = (id: string, layer: number | null, x: number) => ({
  id, key: id, label: id, kind: "function" as const, layer, path: null, local: null, range: null, change: null, x, warn: 0,
});
const board = {
  nodes: [node("A", 3, 0), node("B", 1, -220), node("C", 1, 220), node("D", null, 0)],
  edges: [], flows: [], impacts: [], layers: [{ level: 3, name: "app" }, { level: 1, name: "hal" }],
  about: { intent: "", intent_source: "template", why: [], cls: [], tree: [], drift: [] }, hidden_nodes: 0,
} as Board;

describe("layout", () => {
  it("puts higher layers on top and unlayered nodes last", () => {
    expect([...layerRows(board)]).toEqual([[3, 0], [1, 1], [-1, 2]]);
    const w = worldNodes(board, "layers", { C: { x: 500 } });
    expect(w.get("A")).toEqual({ id: "A", x: 0, y: 105 });
    expect(w.get("C")).toEqual({ id: "C", x: 500, y: 315 });
    expect(w.get("D")!.y).toBe(525);
  });

  it("centres a set of nodes", () => {
    const w = worldNodes(board, "layers", {});
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

const fn = (id: string, layer: number | null = 1, x = 0) => node(id, layer, x);
const fld = (id: string) => ({ ...node(id, 1, 0), kind: "field" as const });
const call = (src: string, dst: string, kind: BoardEdge["kind"] = "call"): BoardEdge =>
  ({ src, dst, kind, status: "unchanged", confidence: "precise" });
const graph = (nodes: BoardNode[], edges: BoardEdge[]) => ({ ...board, nodes, edges, layers: [] }) as Board;

describe("call depth layout", () => {
  it("puts entries on top, callees below and fields under their deepest writer", async () => {
    const { callDepth } = await import("./layout");
    const g = graph([fn("main"), fn("a"), fn("b"), fn("c"), fld("f")],
                    [call("main", "a"), call("main", "b"), call("a", "c"), call("b", "c"), call("c", "f", "writes"), call("a", "f", "reads")]);
    expect(Object.fromEntries(callDepth(g))).toEqual({ main: 0, a: 1, b: 1, c: 2, f: 3 });
  });

  it("places cycles reachable from no entry from the changed functions, isolated nodes on top", async () => {
    const { callDepth } = await import("./layout");
    const changed = { ...fn("x"), change: { kind: "modified" as const, add: 1, rem: 0 } };
    const g = graph([changed, fn("y"), fn("lonely")], [call("x", "y"), call("y", "x")]);
    expect(Object.fromEntries(callDepth(g))).toEqual({ x: 0, y: 1, lonely: 0 });
  });

  it("orders each row to avoid crossings and centres rows on 0", async () => {
    const { depthPositions } = await import("./layout");
    const g = graph([fn("r1"), fn("r2"), fn("a"), fn("b")], [call("r1", "b"), call("r2", "a")]);
    const pos = depthPositions(g);
    expect(Math.sign(pos.get("r1")! - pos.get("r2")!)).toBe(Math.sign(pos.get("b")! - pos.get("a")!));
    expect(pos.get("r1")! + pos.get("r2")!).toBeCloseTo(0);
  });

  it("spaces each row by label width so long names do not overlap", async () => {
    const { depthPositions, nodeWidth } = await import("./layout");
    const long = (id: string) => ({ ...fn(id), label: "git_repository__configmap_lookup_cache_clear_" + id });
    const g = graph([fn("root"), long("a"), long("b"), fn("c")], [call("root", "a"), call("root", "b"), call("root", "c")]);
    const pos = depthPositions(g), byId = new Map(g.nodes.map((n) => [n.id, n]));
    const row = ["a", "b", "c"].sort((x, y) => pos.get(x)! - pos.get(y)!);
    for (let i = 1; i < row.length; i++) {
      const [l, r] = [byId.get(row[i - 1])!, byId.get(row[i])!];
      expect(pos.get(r.id)! - pos.get(l.id)!).toBeGreaterThanOrEqual((nodeWidth(l) + nodeWidth(r)) / 2 + 40);
    }
    expect(nodeWidth(byId.get("a")!)).toBeGreaterThan(nodeWidth(byId.get("c")!));
  });

  it("is preferred when the layers say little", async () => {
    const { preferDepth } = await import("./layout");
    expect(preferDepth(board)).toBe(false);                                       // 3 layers, none dominant
    expect(preferDepth(graph([fn("a", 2), fn("b", 2), fn("c", 2), fn("d", 2)], []))).toBe(true);
    expect(preferDepth(graph([fn("a", 2), fn("b", 2), fn("c", 2), fn("d", 2), fn("e", 1), fn("f", 0)], []))).toBe(false);
    const most = Array.from({ length: 8 }, (_, i) => fn(`n${i}`, 2));
    expect(preferDepth(graph([...most, fn("e", 1), fn("f", 0)], []))).toBe(true);  // 80% in one layer
  });

  it("builds world positions for either layout, honouring 2-D moves", async () => {
    const { bandsFor, worldNodes } = await import("./layout");
    const g = graph([fn("main", 3), fn("a", 1)], [call("main", "a")]);
    const depth = worldNodes(g, "depth", { a: { x: 50, y: 900 } });
    expect(depth.get("main")!.y).toBe(105);
    expect(depth.get("a")).toEqual({ id: "a", x: 50, y: 900 });
    expect(worldNodes(g, "layers", { a: { x: 7 } }).get("a")).toEqual({ id: "a", x: 7, y: 315 });
    expect(bandsFor(g, "depth").map((b) => b.label)).toEqual(["depth 0 · entry", "depth 1"]);
    expect(bandsFor(board, "layers").map((b) => b.label)).toEqual(["L3 · app", "L1 · hal", "other"]);
  });
});
