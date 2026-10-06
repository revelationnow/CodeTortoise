/** Graph zoom (spec §13.4; every graph since 2026-10-05): a scale z applied after the lens, about the canvas centre. */
import { type Lens, makeLens, type View, type Viewport } from "./lens";

export const ZOOM_MIN = 0.5, ZOOM_MAX = 2.5;

/** The lens seen through zoom z: screen = centre + (lensed − centre) · z. Node scale grows with z. */
export function zoomLens(lens: Lens, z: number, vp: Viewport): Lens {
  if (z === 1) return lens;
  const cx = vp.W / 2, cy = vp.H / 2;
  const back = (sx: number) => cx + (sx - cx) / z;
  return {
    project(wx, wy) {
      const p = lens.project(wx, wy);
      return { x: cx + (p.x - cx) * z, y: cy + (p.y - cy) * z, v: p.v, s: p.s * z };
    },
    bandY: (sx, wy) => cy + (lens.bandY(back(sx), wy) - cy) * z,
    unprojectX: (sx) => lens.unprojectX(back(sx)),
    unprojectY: (sx, sy) => lens.unprojectY(back(sx), cy + (sy - cy) / z),
  };
}

const FIT_W = 260, FIT_H = 120;                  // room around the outermost node centres for labels and badges

/** The zoom at which every node fits the canvas (a story's graph opens whole); 1 when it already fits. */
export function fitZoom(nodes: { x: number; y: number }[], vp: Viewport): number {
  if (!nodes.length) return 1;
  const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
  const w = Math.max(...xs) - Math.min(...xs) + FIT_W, h = Math.max(...ys) - Math.min(...ys) + FIT_H;
  return Math.max(ZOOM_MIN, Math.min(1, vp.W / w, vp.H / h));
}

/** The zoom after one pinch update: fingers d0 → d1 apart, clamped to [ZOOM_MIN, ZOOM_MAX]. */
export const pinchZoom = (z0: number, d0: number, d1: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z0 * (d1 / Math.max(1, d0))));

/** The zoom after a wheel or button step of factor k, clamped to [ZOOM_MIN, ZOOM_MAX]. */
export const stepZoom = (z0: number, k: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z0 * k));

/** The pan that puts world point `anchor` (taken under the fingers when the pinch started) under the current pinch
 * midpoint at zoom z1. The lens is non-linear away from the centre, so solve through the real projection: screen x only
 * grows with panX (bisection), and once x is fixed, screen y is linear in panY (one exact step). */
export function pinchView(view: View, z1: number, anchor: { x: number; y: number }, mid: { x: number; y: number }, vp: Viewport,
                          worldXs: number[]): View {
  const at = (v: View) => zoomLens(makeLens(v, vp, worldXs), z1, vp).project(anchor.x, anchor.y);
  let lo = view.panX - 20000, hi = view.panX + 20000;
  for (let i = 0; i < 60; i++) {
    const m = (lo + hi) / 2;
    if (at({ ...view, panX: m }).x < mid.x) lo = m; else hi = m;
  }
  const v = { ...view, panX: (lo + hi) / 2 };
  const y0 = at(v).y, y1 = at({ ...v, panY: v.panY + 1 }).y;
  return Math.abs(y1 - y0) > 1e-6 ? { ...v, panY: v.panY + (mid.y - y0) / (y1 - y0) } : v;
}
