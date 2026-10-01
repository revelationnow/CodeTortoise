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

export function loadMoved(reviewId: number): Record<string, number> {
  const v = load<unknown>(keys.moved(reviewId), {});
  if (!v || typeof v !== "object" || Array.isArray(v)) return {};
  return Object.values(v).every((x) => typeof x === "number" && Number.isFinite(x)) ? (v as Record<string, number>) : {};
}

export function loadWidth(key: string, fallback: number): number {
  const v = load<unknown>(key, fallback);
  return typeof v === "number" && Number.isFinite(v) && v >= 120 && v <= 8000 ? v : fallback;
}
