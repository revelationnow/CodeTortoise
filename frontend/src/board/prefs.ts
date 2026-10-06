/** Per-viewer preferences in localStorage (spec §4.4). Storage may be missing or throw; defaults apply then. */
export function load<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function save(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode, quota, blocked storage: the preference just isn't kept */
  }
}

/** Whose saved state: a review's graph, a story's ("12.S1") or a cluster's ("12.C3"). */
export type BoardKey = number | string;

export const keys = {
  moved: (reviewId: BoardKey) => `ct.board.${reviewId}.moved`,
  layout: (reviewId: BoardKey) => `ct.board.${reviewId}.layout`,
  viewerView: "ct.viewer.view",
  lens: "ct.lens",
  /** The workspace's rail and detail panel widths and which rail sections are open (review workspace §2.2). */
  railW: "ct.ws.railW",
  detailW: "ct.ws.detailW",
  railOpen: "ct.ws.rail.open",
  /** Neighbours drawn as tiles or as the call tree. */
  nbView: "ct.ws.nb.view",
};

/* Typed readers: a value of the wrong shape (another app version, an extension, a manual edit) falls back to the
   default instead of breaking the board. */
export function loadLens(): 0 | 2 | 4 {
  const v = load<unknown>(keys.lens, 2);
  return v === 0 || v === 2 || v === 4 ? v : 2;
}

export function loadLayout(reviewId: BoardKey): "layers" | "depth" | null {
  const v = load<unknown>(keys.layout(reviewId), null);
  return v === "layers" || v === "depth" ? v : null;
}

type Moved = Record<string, { x: number; y?: number }>;
const finite = (x: unknown) => typeof x === "number" && Number.isFinite(x);
const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

/** 2-D moves per layout; also reads the first board's x-only `{id: x}` shape (those were layer-band moves). */
export function loadMovedAll(reviewId: BoardKey): { layers: Moved; depth: Moved } {
  const empty = { layers: {}, depth: {} };
  const v = load<unknown>(keys.moved(reviewId), empty);
  if (!isObj(v)) return empty;
  if (Object.values(v).every(finite))
    return { layers: Object.fromEntries(Object.entries(v).map(([id, x]) => [id, { x: x as number }])), depth: {} };
  const one = (m: unknown): Moved | null => {
    if (m === undefined) return {};
    if (!isObj(m)) return null;
    const ok = Object.values(m).every((p) => isObj(p) && finite(p.x) && (p.y === undefined || finite(p.y)));
    return ok ? (m as Moved) : null;
  };
  const layers = one(v.layers), depth = one(v.depth);
  return layers && depth ? { layers, depth } : empty;
}

export function loadWidth(key: string, fallback: number): number {
  const v = load<unknown>(key, fallback);
  return typeof v === "number" && Number.isFinite(v) && v >= 120 && v <= 8000 ? v : fallback;
}

export type ViewerView = "changes" | "full";
export function loadViewerView(): ViewerView {
  return load<unknown>(keys.viewerView, null) === "full" ? "full" : "changes";
}
