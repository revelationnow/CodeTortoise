/** Per-item memory for the session (spec 2026-10-04-review-workspace §2.4): each item remembers its last view, flow
 * and detail content, so going back to it from the rail returns to where the reader was. */
import { type Address, at, type Place, placeKey } from "./address";

export type Memory = Record<string, Address>;

export function remember(m: Memory, a: Address): Memory {
  return a.place.kind === "unknown" ? m : { ...m, [placeKey(a.place)]: a };
}

export function recall(m: Memory, place: Place): Address {
  return m[placeKey(place)] ?? at(place);
}

const key = (reviewId: number) => `ct.ws.${reviewId}.memory`;

/** Session storage may be missing or throw: the workspace then just forgets. */
export function loadMemory(reviewId: number): Memory {
  try {
    const v = JSON.parse(window.sessionStorage.getItem(key(reviewId)) ?? "{}");
    return v && typeof v === "object" && !Array.isArray(v) ? v as Memory : {};
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
