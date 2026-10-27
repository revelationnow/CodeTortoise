import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { keys } from "../board/prefs";
import { setShortcutsOn, shortcutsOn } from "./shortcuts";

// vitest runs in node here (no jsdom): a Map-backed localStorage, as the other prefs tests do
let store: Map<string, string>;
beforeEach(() => {
  store = new Map();
  vi.stubGlobal("window", { localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) } });
});
afterEach(() => vi.unstubAllGlobals());

describe("the single-key shortcuts switch", () => {
  it("is on until the reader turns it off", () => {
    expect(shortcutsOn()).toBe(true);
  });

  it("is off after setShortcutsOn(false) and on again after setShortcutsOn(true)", () => {
    setShortcutsOn(false);
    expect(shortcutsOn()).toBe(false);
    setShortcutsOn(true);
    expect(shortcutsOn()).toBe(true);
  });

  it("is kept in this browser under ct.ws.shortcuts, and read afresh each time, for a key press to meet it", () => {
    expect(keys.shortcuts).toBe("ct.ws.shortcuts");
    setShortcutsOn(false);
    expect(store.get("ct.ws.shortcuts")).toBe("false");
    store.set("ct.ws.shortcuts", "true");                               // another tab switched it on
    expect(shortcutsOn()).toBe(true);
    store.set("ct.ws.shortcuts", "false");
    expect(shortcutsOn()).toBe(false);
  });

  it("stays on when what is stored is not a false: junk, another type, nothing", () => {
    for (const stored of ["{not json", '"false"', "0", "null", "[]", '"off"']) {
      store.set("ct.ws.shortcuts", stored);
      expect(shortcutsOn(), `stored ${stored}`).toBe(true);
    }
  });

  it("is on, and nothing throws, when storage is blocked", () => {
    vi.stubGlobal("window", { localStorage: { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("quota"); } } });
    expect(shortcutsOn()).toBe(true);
    expect(() => setShortcutsOn(false)).not.toThrow();
    expect(shortcutsOn()).toBe(true);                                   // nothing was kept: the keys work
    vi.stubGlobal("window", { get localStorage(): Storage { throw new Error("SecurityError"); } });   // the browser refuses even the property
    expect(shortcutsOn()).toBe(true);
    expect(() => setShortcutsOn(true)).not.toThrow();
  });
});
