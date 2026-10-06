/** Per-item memory for the session (spec 2026-10-04-review-workspace §2.4): each item remembers its last view, flow
 * and detail content, so going back to it from the rail returns to where the reader was. */
import { type Address, at, type Open, type Place, placeKey } from "./address";

export type Memory = Record<string, Address>;

export function remember(m: Memory, a: Address): Memory {
  if (a.place.kind === "unknown") return m;
  const { story: _lit, ...kept } = a;                       // a story lit on a map is for that visit only
  return { ...m, [placeKey(a.place)]: kept };
}

export function recall(m: Memory, place: Place): Address {
  return m[placeKey(place)] ?? at(place);
}

const key = (reviewId: number) => `ct.ws.${reviewId}.memory`;

type Loose = Record<string, unknown>;
const isObj = (v: unknown): v is Loose => !!v && typeof v === "object" && !Array.isArray(v);
const str = (v: unknown) => typeof v === "string" && v !== "";

function isPlace(p: unknown): p is Place {
  if (!isObj(p)) return false;
  switch (p.kind) {
    case "whole": return p.view === undefined || p.view === "graph";
    case "story": return str(p.sid) && (p.view === "steps" || p.view === "graph");
    case "finding": return str(p.fid);
    case "cl": return Number.isInteger(p.cl);
    case "cluster": return str(p.cid);
    default: return false;
  }
}

function isOpen(o: unknown): o is Open {
  if (o === null) return true;
  if (!isObj(o)) return false;
  if ("node" in o) return str(o.node);
  return str(o.file) && (o.line === null || (Number.isInteger(o.line) && (o.line as number) > 0));
}

/** A stored entry is used only if it is an address filed under its own item. */
const isAddressAt = (k: string, a: unknown): a is Address =>
  isObj(a) && isPlace(a.place) && placeKey(a.place) === k && isOpen(a.open)
  && (a.flow === null || (Number.isInteger(a.flow) && (a.flow as number) > 0)) && (a.tab === "diff" || a.tab === "neighbours");

/** Session storage may be missing or throw: the workspace then just forgets. */
export function loadMemory(reviewId: number): Memory {
  try {
    const v: unknown = JSON.parse(window.sessionStorage.getItem(key(reviewId)) ?? "{}");
    return isObj(v) ? Object.fromEntries(Object.entries(v).filter(([k, a]) => isAddressAt(k, a))) as Memory : {};
  } catch {
    return {};
  }
}

export function saveMemory(reviewId: number, m: Memory): void {
  try {
    window.sessionStorage.setItem(key(reviewId), JSON.stringify(m));
  } catch {
    /* private mode or blocked storage: items open at their defaults */
  }
}
