import { describe, expect, it } from "vitest";
import type { Board, BoardNode, StoryDetail } from "../board/types";
import { detailBoards, locateNode } from "./detail";

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

describe("detailBoards", () => {
  const story = (graph: Board | null, b: Board) => ({ board: b, graph }) as StoryDetail;

  it("on a split review, finds a field without a story folded into the story being read", () => {
    const s = node("N5", { kind: "struct", path: "//d/a.h", range: [1, 4], fields: [{ id: "N6", label: "errors" }] });
    const graph = board([s]);
    expect(locateNode("N6", detailBoards(null, story(graph, board([])), null))).toEqual({ node: s, board: graph });
  });

  it("finds a context function's slice on the cluster being read", () => {
    const f = node("N7", { path: "//d/b.c", range: [10, 20] }), cluster = board([f]);
    expect(locateNode("N7", detailBoards(null, cluster, null))).toEqual({ node: f, board: cluster });
  });

  it("looks on the node's own story first, then the place, then the one board", () => {
    const own = board([node("N1", { path: "//d/a.c", range: [1, 2] })]), here = board([node("N1", { path: "//d/a.c", range: [5, 6] })]);
    const whole = board([]);
    expect(detailBoards(story(null, own), here, whole)).toEqual([null, own, here, whole]);
  });
});
