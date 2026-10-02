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
    const { loadLens, loadMovedAll, loadWidth } = await import("./prefs");
    stub({ "ct.lens": "4", "ct.board.1.moved": '{"N1": 40, "N2": -3.5}', "ct.panel.aboutW": "420" });
    expect([loadLens(), loadMovedAll(1), loadWidth(keys.aboutW, 360)])
      .toEqual([4, { layers: { N1: { x: 40 }, N2: { x: -3.5 } }, depth: {} }, 420]);
  });

  it("fall back on wrong shapes", async () => {
    const { loadLens, loadMovedAll, loadWidth } = await import("./prefs");
    for (const [lens, moved, width] of [["3", "null", "null"], ['"2"', "[1,2]", '"wide"'], ["null", '{"N1": "x"}', "-5"],
                                        ["2.5", '{"N1": null}', "1e9"]]) {
      stub({ "ct.lens": lens, "ct.board.1.moved": moved, "ct.panel.aboutW": width });
      expect([loadLens(), loadMovedAll(1), loadWidth(keys.aboutW, 360)]).toEqual([2, { layers: {}, depth: {} }, 360]);
    }
  });
});

describe("layout prefs", () => {
  const stub = (values: Record<string, string>) =>
    vi.stubGlobal("window", { innerWidth: 1400, localStorage: { getItem: (k: string) => values[k] ?? null, setItem: () => {} } });

  it("read 2-D moves per layout and the old x-only shape", async () => {
    const { loadLayout, loadMovedAll } = await import("./prefs");
    stub({ "ct.board.1.moved": '{"N1": 40}', "ct.board.1.layout": '"depth"' });
    expect(loadMovedAll(1)).toEqual({ layers: { N1: { x: 40 } }, depth: {} });
    expect(loadLayout(1)).toBe("depth");
    stub({ "ct.board.1.moved": '{"layers": {"N1": {"x": 1, "y": 2}}, "depth": {"N2": {"x": 3}}}' });
    expect(loadMovedAll(1)).toEqual({ layers: { N1: { x: 1, y: 2 } }, depth: { N2: { x: 3 } } });
    expect(loadLayout(1)).toBeNull();
    stub({ "ct.board.1.moved": '{"layers": {"N1": {"x": "a"}}}', "ct.board.1.layout": '"sideways"' });
    expect(loadMovedAll(1)).toEqual({ layers: {}, depth: {} });
    expect(loadLayout(1)).toBeNull();
  });
});

describe("panel prefs", () => {
  const stub = (values: Record<string, string>) =>
    vi.stubGlobal("window", { innerWidth: 1400, localStorage: { getItem: (k: string) => values[k] ?? null, setItem: () => {} } });

  it("remember whether the change panel is open, and the flow bar height", async () => {
    const { loadAboutOpen, loadSize } = await import("./prefs");
    stub({ "ct.panel.about": "false", "ct.panel.flowH": "180" });
    expect(loadAboutOpen()).toBe(false);
    expect(loadSize(keys.flowH, 40, 4000)).toBe(180);
    stub({ "ct.panel.about": '"yes"', "ct.panel.flowH": "12" });
    expect(loadAboutOpen()).toBeNull();
    expect(loadSize(keys.flowH, 40, 4000)).toBeNull();
    stub({});
    expect(loadAboutOpen()).toBeNull();
    expect(loadSize(keys.flowH, 40, 4000)).toBeNull();
  });
});

describe("phone tab pref", () => {
  it("remembers the tab per review and ignores junk", async () => {
    const { loadTab } = await import("./prefs");
    vi.stubGlobal("window", { localStorage: { getItem: (k: string) => (k === "ct.board.3.tab" ? '"map"' : '"other"'), setItem: () => {} } });
    expect(loadTab(3)).toBe("map");
    expect(loadTab(4)).toBeNull();
  });
});
