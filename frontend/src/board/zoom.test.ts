import { describe, expect, it } from "vitest";
import { makeLens } from "./lens";
import { pinchZoom, zoomLens } from "./zoom";

const vp = { W: 400, H: 700 };
const lens = makeLens({ panX: 200, panY: 0, lens: 0 }, vp, [-500, 500]);

describe("phone zoom", () => {
  it("scales about the canvas centre and inverts", () => {
    const z = zoomLens(lens, 2, vp);
    expect(z.project(0, 350)).toMatchObject({ x: 200, y: 350 });          // the centre stays put
    expect(z.project(50, 400)).toMatchObject({ x: 300, y: 450 });
    expect(z.project(50, 400).s).toBe(2);
    expect(z.unprojectX(300)).toBeCloseTo(50, 3);
    expect(z.unprojectY(300, 450)).toBeCloseTo(400, 3);
    expect(zoomLens(lens, 1, vp)).toBe(lens);
  });

  it("scales by the finger spread, clamped", () => {
    expect(pinchZoom(1, 100, 200)).toBe(2);
    expect(pinchZoom(2, 100, 1000)).toBe(2.5);
    expect(pinchZoom(1, 100, 10)).toBe(0.5);
  });
});

describe("pinch keeps the point under the fingers", () => {
  it("in the lens's folded rim too", async () => {
    const { pinchView } = await import("./zoom");
    const xs = [-1500, -600, 0, 600, 1500];
    for (const mid of [{ x: 200, y: 350 }, { x: 40, y: 600 }, { x: 370, y: 90 }]) {
      const view = { panX: 120, panY: -40, lens: 2 as const };
      const before = zoomLens(makeLens(view, vp, xs), 1, vp);
      const wx = before.unprojectX(mid.x), wy = before.unprojectY(mid.x, mid.y);
      const next = pinchView(view, 1.8, { x: wx, y: wy }, mid, vp, xs);
      const after = zoomLens(makeLens(next, vp, xs), 1.8, vp).project(wx, wy);
      expect(Math.abs(after.x - mid.x)).toBeLessThan(1);
      expect(Math.abs(after.y - mid.y)).toBeLessThan(1);
    }
  });

  it("follows the fingers when they move together (two-finger pan)", async () => {
    const { pinchView } = await import("./zoom");
    const xs = [-1500, 0, 1500], view = { panX: 200, panY: 0, lens: 2 as const };
    const next = pinchView(view, 1.5, { x: 0, y: 350 }, { x: 260, y: 380 }, vp, xs);
    const p = zoomLens(makeLens(next, vp, xs), 1.5, vp).project(0, 350);
    expect([Math.round(p.x), Math.round(p.y)]).toEqual([260, 380]);
  });
});
