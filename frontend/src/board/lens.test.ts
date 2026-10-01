import { describe, expect, it } from "vitest";
import { FLAT, makeLens, vSqueeze } from "./lens";

const vp = { W: 1000, H: 800 };
const xs = Array.from({ length: 41 }, (_, i) => -2000 + i * 100);   // nodes from -2000 to 2000

describe("lens", () => {
  it("is 1:1 inside the flat zone", () => {
    const lens = makeLens({ panX: 500, panY: 100, lens: 2 }, vp, xs);
    for (const wx of [-270, -100, 0, 150, 270]) {
      const p = lens.project(wx, 300);
      expect(p.x).toBeCloseTo(wx + 500);
      expect(p.y).toBeCloseTo(400);
      expect(p.s).toBeCloseTo(1);
    }
  });

  it("folds both sides symmetrically around the focus", () => {
    const lens = makeLens({ panX: 500, panY: 0, lens: 2 }, vp, xs);
    for (const d of [300, 600, 1200, 1900]) {
      const r = lens.project(d, 0).x - 500, l = lens.project(-d, 0).x - 500;
      expect(r).toBeCloseTo(-l);
      expect(Math.abs(r)).toBeLessThan(500);
    }
  });

  it("is monotonic and keeps every node on screen", () => {
    for (const m of [2, 4] as const) {
      const lens = makeLens({ panX: 300, panY: 0, lens: m }, vp, xs);
      let prev = -Infinity;
      for (const wx of xs) {
        const x = lens.project(wx, 0).x;
        expect(x).toBeGreaterThan(prev);
        expect(x).toBeGreaterThanOrEqual(0);
        expect(x).toBeLessThanOrEqual(vp.W);
        prev = x;
      }
    }
  });

  it("has no kink where the flat zone ends", () => {
    const lens = makeLens({ panX: 500, panY: 0, lens: 4 }, vp, xs);
    const F = FLAT * 500;
    const inside = lens.project(F - 1, 0).x - lens.project(F - 2, 0).x;
    const outside = lens.project(F + 2, 0).x - lens.project(F + 1, 0).x;
    expect(outside).toBeCloseTo(inside, 1);
  });

  it("unprojectX inverts the horizontal mapping", () => {
    const lens = makeLens({ panX: 420, panY: 0, lens: 2 }, vp, xs);
    for (const wx of [-1500, -300, 0, 77, 900, 1800]) expect(lens.unprojectX(lens.project(wx, 0).x)).toBeCloseTo(wx, 0);
  });

  it("squeezes y towards the centre line only beyond the flat zone", () => {
    expect(vSqueeze(0.3, 2)).toBe(1);
    expect(vSqueeze(FLAT, 2)).toBe(1);
    expect(vSqueeze(1, 2)).toBeCloseTo(0.7);
    expect(vSqueeze(1, 4)).toBeCloseTo(0.55);
    const lens = makeLens({ panX: 500, panY: 0, lens: 2 }, vp, xs);
    const rim = lens.project(1900, 100), mid = lens.project(0, 100);
    expect(mid.y).toBeCloseTo(100);
    expect(rim.y).toBeGreaterThan(100);          // pulled towards H/2 = 400
    expect(rim.y).toBeLessThan(400);
    expect(lens.bandY(500, 100)).toBeCloseTo(100);
  });

  it("is the identity (plus pan) when off", () => {
    const lens = makeLens({ panX: 10, panY: 20, lens: 0 }, vp, xs);
    expect(lens.project(1900, 700)).toEqual({ x: 1910, y: 720, v: 1, s: 1 });
    expect(lens.unprojectX(1910)).toBeCloseTo(1900, 0);
  });
});

describe("unprojectY", () => {
  it("inverts the vertical mapping at any screen x, lens on or off", () => {
    for (const m of [0, 2, 4] as const) {
      const lens = makeLens({ panX: 300, panY: -40, lens: m }, vp, xs);
      for (const [wx, wy] of [[0, 100], [1500, 700], [-1800, -50], [600, 400]]) {
        const p = lens.project(wx, wy);
        expect(lens.unprojectY(p.x, p.y)).toBeCloseTo(wy, 3);
      }
    }
  });
});
