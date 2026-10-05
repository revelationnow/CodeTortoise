import { describe, expect, it } from "vitest";
import { type GraphAction, initialGraph, reduceGraph } from "./reducer";

const run = (...actions: GraphAction[]) => actions.reduce(reduceGraph, initialGraph());

describe("the graph's state", () => {
  it("node moves are 2-D, kept per layout and reset per layout", () => {
    let s = run({ t: "node.move", id: "N1", x: 10, y: 20 }, { t: "layout", layout: "depth" }, { t: "node.move", id: "N1", x: 5, y: 6 });
    expect(s.moved).toEqual({ layers: { N1: { x: 10, y: 20 } }, depth: { N1: { x: 5, y: 6 } } });
    s = reduceGraph(s, { t: "layout.reset" });
    expect(s.moved).toEqual({ layers: { N1: { x: 10, y: 20 } }, depth: {} });
  });

  it("lens, pan and mode", () => {
    const s = run({ t: "lens", lens: 4 }, { t: "pan", panX: 3, panY: -2 }, { t: "mode", mode: "graph" });
    expect(s.view).toEqual({ panX: 3, panY: -2, lens: 4 });
    expect(s.mode).toBe("graph");
  });

  it("starts on the flows at the given lens and layout", () => {
    expect(initialGraph(0, { layers: {}, depth: {} }, "depth")).toEqual(
      { view: { panX: 0, panY: 0, lens: 0 }, mode: "flows", layout: "depth", moved: { layers: {}, depth: {} } });
  });
});
