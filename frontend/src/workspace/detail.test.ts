import { describe, expect, it } from "vitest";
import type { Board, BoardNode } from "../board/types";
import { locateNode } from "./detail";

const node = (id: string, extra: Partial<BoardNode> = {}): BoardNode => ({
  id, key: id, label: id, kind: "function", layer: null, path: null, local: null, range: null, change: null, x: 0, warn: 0, ...extra,
});
const board = (nodes: BoardNode[]): Board => ({ nodes, edges: [], flows: [], impacts: [], layers: [], hidden_nodes: 0,
  about: { intent: "", intent_source: "template", why: [], cls: [], tree: [], drift: [] } });

describe("locateNode", () => {
  it("finds a node with code on the first board that has it", () => {
    const a = board([node("N1")]), b = board([node("N1", { path: "//d/a.c", range: [3, 9] })]);
    expect(locateNode("N1", [undefined, a, b])).toEqual({ node: b.nodes[0], board: b });
  });

  it("finds a field folded into a struct as the struct", () => {
    const s = node("N5", { kind: "struct", path: "//d/a.h", range: [1, 4], fields: [{ id: "N6", label: "errors" }] });
    const b = board([s]);
    expect(locateNode("N6", [b])).toEqual({ node: s, board: b });
  });

  it("falls back to a node without code, then to nothing", () => {
    const a = board([node("N1")]);
    expect(locateNode("N1", [a])).toEqual({ node: a.nodes[0], board: a });
    expect(locateNode("N2", [a, null])).toBeNull();
  });
});
