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

export const keys = {
  moved: (reviewId: number) => `ct.board.${reviewId}.moved`,
  layout: (reviewId: number) => `ct.board.${reviewId}.layout`,
  about: "ct.panel.about",
  flowH: "ct.panel.flowH",
  tab: (reviewId: number) => `ct.board.${reviewId}.tab`,
  viewerW: "ct.panel.viewerW",
  aboutW: "ct.panel.aboutW",
  lens: "ct.lens",
};

/* Typed readers: a value of the wrong shape (another app version, an extension, a manual edit) falls back to the
   default instead of breaking the board. */
export function loadLens(): 0 | 2 | 4 {
  const v = load<unknown>(keys.lens, 2);
  return v === 0 || v === 2 || v === 4 ? v : 2;
}

export function loadLayout(reviewId: number): "layers" | "depth" | null {
  const v = load<unknown>(keys.layout(reviewId), null);
  return v === "layers" || v === "depth" ? v : null;
}

type Moved = Record<string, { x: number; y?: number }>;
const finite = (x: unknown) => typeof x === "number" && Number.isFinite(x);
const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

/** 2-D moves per layout; also reads the first board's x-only `{id: x}` shape (those were layer-band moves). */
export function loadMovedAll(reviewId: number): { layers: Moved; depth: Moved } {
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

export function loadAboutOpen(): boolean | null {
  const v = load<unknown>(keys.about, null);
  return typeof v === "boolean" ? v : null;
}

export function loadSize(key: string, min: number, max: number): number | null {
  const v = load<unknown>(key, null);
  return typeof v === "number" && Number.isFinite(v) && v >= min && v <= max ? v : null;
}

export type PhoneTab = "flows" | "map" | "files" | "summary";
export function loadTab(reviewId: number): PhoneTab | null {
  const v = load<unknown>(keys.tab(reviewId), null);
  return v === "flows" || v === "map" || v === "files" || v === "summary" ? v : null;
}
