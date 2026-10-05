import { describe, expect, it } from "vitest";
import type { BoardFlow } from "../board/types";
import { drawnIndex, pickFlow, wrap } from "./flows";

const flow = (id: string, path: string[]) => ({ id, path } as BoardFlow);
const flows = [flow("FL1", ["N1", "N2"]), flow("FL2", ["N3", "N4"]), flow("FL3", ["N5"])];

describe("the selected flow", () => {
  it("is the address's flow (1-based), kept in range", () => {
    expect(pickFlow(flows, 2, null)).toBe(1);
    expect(pickFlow(flows, 9, null)).toBe(2);
  });

  it("else the first flow through the open node, else the first", () => {
    expect(pickFlow(flows, null, "N4")).toBe(1);
    expect(pickFlow(flows, null, "N99")).toBe(0);
    expect(pickFlow([], null, null)).toBe(0);
  });

  it("steps wrap around", () => {
    expect(wrap(0, -1, 3)).toBe(2);
    expect(wrap(2, 1, 3)).toBe(0);
    expect(wrap(0, 1, 0)).toBe(0);
  });
});

describe("a story's flow on its graph", () => {
  it("is found by id, whatever its place among the graph's flows", () => {
    expect(drawnIndex(flows, 1, [flows[1]])).toBe(0);
    expect(drawnIndex(flows, 2, [flows[2], flows[0]])).toBe(0);
  });

  it("is -1 when the graph leaves it out (its path is too long to draw)", () => {
    expect(drawnIndex(flows, 0, [flows[1]])).toBe(-1);
    expect(drawnIndex([], 0, flows)).toBe(-1);
  });
});
