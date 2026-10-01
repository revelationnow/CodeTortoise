import { afterEach, describe, expect, it, vi } from "vitest";
import { keys, load, save } from "./prefs";

afterEach(() => vi.unstubAllGlobals());

describe("prefs", () => {
  it("round-trips through localStorage", () => {
    const store = new Map<string, string>();
    vi.stubGlobal("window", { localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) } });
    save(keys.moved(7), { N1: 40 });
    expect(load(keys.moved(7), {})).toEqual({ N1: 40 });
    expect(load(keys.lens, 2)).toBe(2);
  });

  it("falls back when storage throws or holds junk", () => {
    vi.stubGlobal("window", { localStorage: { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("quota"); } } });
    expect(load(keys.lens, 2)).toBe(2);
    expect(() => save(keys.lens, 4)).not.toThrow();
    vi.stubGlobal("window", { localStorage: { getItem: () => "{not json", setItem: () => {} } });
    expect(load(keys.aboutW, 360)).toBe(360);
  });
});
