import { describe, expect, it } from "vitest";
import { dragSize } from "./resize";

describe("dragSize", () => {
  it("grows towards the side the grip faces", () => {
    expect(dragSize(400, "left", 500, 420, 200, 900)).toBe(480);     // viewer: grip on its left edge, drag left
    expect(dragSize(360, "right", 300, 420, 200, 900)).toBe(480);    // change panel on the left: grip on its right edge
    expect(dragSize(120, "bottom", 200, 260, 40, 450)).toBe(180);    // flow bar: grip on its bottom edge
  });

  it("clamps to the limits and rounds", () => {
    expect(dragSize(400, "left", 500, 900, 200, 900)).toBe(200);
    expect(dragSize(360, "right", 300, 2000, 200, 900)).toBe(900);
    expect(dragSize(120, "bottom", 200, 200.6, 40, 450)).toBe(121);
  });
});
