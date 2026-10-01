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

describe("typed prefs", () => {
  const stub = (values: Record<string, string>) =>
    vi.stubGlobal("window", { innerWidth: 1400, localStorage: { getItem: (k: string) => values[k] ?? null, setItem: () => {} } });

  it("accept only well-formed values", async () => {
    const { loadLens, loadMoved, loadWidth } = await import("./prefs");
    stub({ "ct.lens": "4", "ct.board.1.moved": '{"N1": 40, "N2": -3.5}', "ct.panel.aboutW": "420" });
    expect([loadLens(), loadMoved(1), loadWidth(keys.aboutW, 360)]).toEqual([4, { N1: 40, N2: -3.5 }, 420]);
  });

  it("fall back on wrong shapes", async () => {
    const { loadLens, loadMoved, loadWidth } = await import("./prefs");
    for (const [lens, moved, width] of [["3", "null", "null"], ['"2"', "[1,2]", '"wide"'], ["null", '{"N1": "x"}', "-5"],
                                        ["2.5", '{"N1": null}', "1e9"]]) {
      stub({ "ct.lens": lens, "ct.board.1.moved": moved, "ct.panel.aboutW": width });
      expect([loadLens(), loadMoved(1), loadWidth(keys.aboutW, 360)]).toEqual([2, {}, 360]);
    }
  });
});
