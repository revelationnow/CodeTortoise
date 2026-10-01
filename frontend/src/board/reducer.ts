/** Board state machine (spec §3.7, §4.3). Pure: every interaction is one transition. */
import type { LensStrength, View } from "./lens";

export interface CardState { collapsed: boolean; offset?: { x: number; y: number } }
export interface Reveal { path: string; line: number | null; seq: number }
export interface ViewerState {
  files: string[];                          // newest first
  collapsed: string[];
  mode: "unified" | "split" | null;         // chosen on first open from the screen width
  snapshot: Record<string, boolean> | null; // card collapse state from before the viewer opened
  reveal: Reveal | null;                    // last file/line to scroll to (seq bumps on every open)
}
export interface BoardState {
  cards: Record<string, CardState>;
  z: string[];                              // stacking order, last = front
  viewer: ViewerState;
  view: View;
  mode: "flows" | "graph";
  flow: number;
  about: boolean;
  moved: Record<string, number>;            // node id -> world x chosen by this viewer
}

export type Action =
  | { t: "card.open"; id: string }
  | { t: "card.toggle"; id: string }
  | { t: "card.front"; id: string }
  | { t: "card.expand"; id: string }
  | { t: "card.move"; id: string; offset: { x: number; y: number } }
  | { t: "card.unpin"; id: string }
  | { t: "card.close"; id: string }
  | { t: "card.closeAll" }
  | { t: "viewer.open"; path: string; line?: number | null; wide: boolean }
  | { t: "viewer.toggle"; path: string }
  | { t: "viewer.expandAll" }
  | { t: "viewer.collapseAll" }
  | { t: "viewer.mode"; mode: "unified" | "split" }
  | { t: "viewer.close"; path: string }
  | { t: "viewer.closeAll" }
  | { t: "flow"; i: number }
  | { t: "mode"; mode: "flows" | "graph" }
  | { t: "lens"; lens: LensStrength }
  | { t: "node.move"; id: string; x: number }
  | { t: "layout.reset" }
  | { t: "about.toggle"; open?: boolean }
  | { t: "pan"; panX: number; panY: number };

export function initialState(lens: LensStrength = 2, moved: Record<string, number> = {}): BoardState {
  return {
    cards: {}, z: [], viewer: { files: [], collapsed: [], mode: null, snapshot: null, reveal: null },
    view: { panX: 0, panY: 0, lens }, mode: "flows", flow: 0, about: false, moved,
  };
}

const front = (z: string[], id: string) => [...z.filter((x) => x !== id), id];
const without = <T,>(rec: Record<string, T>, key: string) => {
  const { [key]: _, ...rest } = rec;
  return rest;
};

function closeViewer(s: BoardState): BoardState {
  const cards = { ...s.cards };
  for (const [id, collapsed] of Object.entries(s.viewer.snapshot ?? {}))
    if (cards[id]) cards[id] = { ...cards[id], collapsed };
  return { ...s, cards, viewer: { ...s.viewer, files: [], collapsed: [], snapshot: null } };
}

export function reduce(s: BoardState, a: Action): BoardState {
  const v = s.viewer;
  switch (a.t) {
    case "card.open": {                     // open, or expand / bring to front — never closes
      const c = s.cards[a.id];
      const next = c ? { ...c, collapsed: false } : { collapsed: v.files.length > 0 };
      return { ...s, cards: { ...s.cards, [a.id]: next }, z: front(s.z, a.id) };
    }
    case "card.toggle": {                   // flow-summary step chips: open <-> close
      const c = s.cards[a.id];
      return c && !c.collapsed ? reduce(s, { t: "card.close", id: a.id }) : reduce(s, { t: "card.open", id: a.id });
    }
    case "card.front":
      return s.cards[a.id] ? { ...s, z: front(s.z, a.id) } : s;
    case "card.expand":
      if (!s.cards[a.id]) return s;
      return { ...s, cards: { ...s.cards, [a.id]: { ...s.cards[a.id], collapsed: false } }, z: front(s.z, a.id) };
    case "card.move":
      if (!s.cards[a.id]) return s;
      return { ...s, cards: { ...s.cards, [a.id]: { ...s.cards[a.id], offset: a.offset } } };
    case "card.unpin": {
      const c = s.cards[a.id];
      if (!c) return s;
      return { ...s, cards: { ...s.cards, [a.id]: { collapsed: c.collapsed } } };
    }
    case "card.close": {
      const snapshot = v.snapshot && a.id in v.snapshot ? without(v.snapshot, a.id) : v.snapshot;
      return { ...s, cards: without(s.cards, a.id), z: s.z.filter((x) => x !== a.id), viewer: { ...v, snapshot } };
    }
    case "card.closeAll":
      return { ...s, cards: {}, z: [], viewer: { ...v, snapshot: v.snapshot ? {} : null } };
    case "viewer.open": {
      let cards = s.cards, snapshot = v.snapshot, mode = v.mode;
      if (!v.files.length) {                // first file: collapse every card to a pill, remember how they were
        snapshot = Object.fromEntries(Object.entries(s.cards).map(([id, c]) => [id, c.collapsed]));
        cards = Object.fromEntries(Object.entries(s.cards).map(([id, c]) => [id, { ...c, collapsed: true }]));
        mode = mode ?? (a.wide ? "split" : "unified");
      }
      const files = [a.path, ...v.files.filter((p) => p !== a.path)];
      const reveal = { path: a.path, line: a.line ?? null, seq: (v.reveal?.seq ?? 0) + 1 };
      return { ...s, cards, viewer: { files, collapsed: v.collapsed.filter((p) => p !== a.path), mode, snapshot, reveal } };
    }
    case "viewer.toggle": {
      const collapsed = v.collapsed.includes(a.path) ? v.collapsed.filter((p) => p !== a.path) : [...v.collapsed, a.path];
      return { ...s, viewer: { ...v, collapsed } };
    }
    case "viewer.expandAll":
      return { ...s, viewer: { ...v, collapsed: [] } };
    case "viewer.collapseAll":
      return { ...s, viewer: { ...v, collapsed: [...v.files] } };
    case "viewer.mode":
      return { ...s, viewer: { ...v, mode: a.mode } };
    case "viewer.close": {
      const files = v.files.filter((p) => p !== a.path);
      if (!files.length) return closeViewer(s);
      return { ...s, viewer: { ...v, files, collapsed: v.collapsed.filter((p) => p !== a.path) } };
    }
    case "viewer.closeAll":
      return v.files.length ? closeViewer(s) : s;
    case "flow":
      return { ...s, flow: a.i, mode: "flows" };
    case "mode":
      return { ...s, mode: a.mode };
    case "lens":
      return { ...s, view: { ...s.view, lens: a.lens } };
    case "node.move":
      return { ...s, moved: { ...s.moved, [a.id]: a.x } };
    case "layout.reset":
      return { ...s, moved: {} };
    case "about.toggle":
      return { ...s, about: a.open ?? !s.about };
    case "pan":
      return { ...s, view: { ...s.view, panX: a.panX, panY: a.panY } };
  }
}
