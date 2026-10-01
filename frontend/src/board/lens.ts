/** Cylindrical lens for the board (spec §3.1): 1:1 in the middle, Sarkar–Brown fold towards the left/right rims,
 * layers converge vertically near the rims. Pure functions — everything on the board goes through the same mapping. */

export const BAND = 210;                   // world height of a layer band
export const FLAT = 0.55;                  // fraction of the half-width that stays 1:1
export const PAD = 140;                    // world padding beyond the farthest node
export const FOLD: Record<number, number> = { 2: 1.8, 4: 3.4 };

export type LensStrength = 0 | 2 | 4;
export interface View { panX: number; panY: number; lens: LensStrength }
export interface Viewport { W: number; H: number }
export interface Projected { x: number; y: number; v: number; s: number }
export interface Lens {
  project(wx: number, wy: number): Projected;
  bandY(screenX: number, worldY: number): number;
  unprojectX(screenX: number): number;
  unprojectY(screenX: number, screenY: number): number;
}

/** Vertical squeeze factor at normalised horizontal distance nd (0 at the focus, 1 at the rim). */
export function vSqueeze(nd: number, m: LensStrength): number {
  if (nd <= FLAT) return 1;
  const vmin = m >= 4 ? 0.55 : 0.7;
  const t = Math.min(1, (nd - FLAT) / (1 - FLAT)), e = t * t * (3 - 2 * t);
  return 1 - (1 - vmin) * e;
}

export function makeLens(view: View, vp: Viewport, worldXs: number[]): Lens {
  const { W, H } = vp, m = view.lens, half = W / 2;
  const focusX = half - view.panX;                        // world x under the canvas centre
  const minX = worldXs.length ? Math.min(...worldXs) : focusX, maxX = worldXs.length ? Math.max(...worldXs) : focusX;
  const extent = (dir: number) => Math.max(0, dir > 0 ? maxX - focusX : focusX - minX) + PAD;

  function axis(w: number): [number, number] {           // world offset from the focus -> [screen x, local scale]
    if (!m) return [half + w, 1];
    const F = FLAT * half, R = half - F, a = Math.abs(w), dir = Math.sign(w) || 1;
    if (a <= F) return [half + w, 1];
    const Rw = Math.max(extent(dir) - F, R * FOLD[m]);   // world span folded into the remaining screen span R
    const k = Rw / R - 1, t = Math.min((a - F) / Rw, 1); // slope 1 at the seam: no kink
    const g = k > 0 ? ((k + 1) * t) / (k * t + 1) : t;
    return [half + dir * (F + R * g), Math.max(0.34, 1 / Math.pow(k * t + 1, 2))];
  }
  const squeeze = (sx: number) => (m ? vSqueeze(Math.min(1, Math.abs(sx - half) / half), m) : 1);

  function project(wx: number, wy: number): Projected {
    const [x, kx] = axis(wx + view.panX - half);
    const v = squeeze(x);
    const y = H / 2 + (wy + view.panY - H / 2) * v;
    return { x, y, v, s: m ? Math.max(0.36, Math.min(1, kx) * (0.45 + 0.55 * v)) : 1 };
  }
  function bandY(screenX: number, worldY: number): number {
    return H / 2 + (worldY + view.panY - H / 2) * squeeze(screenX);
  }
  function unprojectX(screenX: number): number {         // bisection: the horizontal mapping is monotonic
    let lo = focusX - 40000, hi = focusX + 40000;
    for (let i = 0; i < 64; i++) {
      const mid = (lo + hi) / 2;
      if (project(mid, 0).x < screenX) lo = mid; else hi = mid;
    }
    return (lo + hi) / 2;
  }
  function unprojectY(screenX: number, screenY: number): number {   // inverse of the vertical squeeze at that x
    return (screenY - H / 2) / squeeze(screenX) + H / 2 - view.panY;
  }
  return { project, bandY, unprojectX, unprojectY };
}
