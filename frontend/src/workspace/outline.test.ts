import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BAR, barPin, loadThread, openThread, pinnedSpace, saveThread } from "./outline";

const threads = [{ id: "T1", stories: ["S2", "S1"] }, { id: "T2", stories: ["S3", "S5"] }, { id: "T3", stories: ["S4"] }];

describe("which thread the outline opens (spec 2026-10-25-review-ui-redesign §6)", () => {
  it("opens the thread holding the current story, whatever was opened last", () => {
    expect(openThread(threads, "S5", "T1")).toBe("T2");
    expect(openThread(threads, "S1", null)).toBe("T1");
  });

  it("elsewhere opens the thread last opened if the reading still has it, else none", () => {
    expect(openThread(threads, null, "T3")).toBe("T3");
    expect(openThread(threads, "S9", "T3")).toBe("T3");                      // a story in no thread
    expect(openThread(threads, null, "T9")).toBeNull();
    expect(openThread(threads, null, null)).toBeNull();
    expect(openThread([], "S1", "T1")).toBeNull();
  });
});

describe("where the closed bars pin (§6)", () => {
  it("pins the bars up to the open one at the top, stacked, and the rest at the bottom, stacked from the last", () => {
    expect(BAR).toBe(36);
    expect([0, 1, 2, 3].map((i) => barPin(i, 1, 4))).toEqual([{ top: 0 }, { top: 36 }, { bottom: 36 }, { bottom: 0 }]);
    expect([0, 1, 2].map((i) => barPin(i, 2, 3))).toEqual([{ top: 0 }, { top: 36 }, { top: 72 }]);
    expect([0, 1].map((i) => barPin(i, 0, 2))).toEqual([{ top: 0 }, { bottom: 0 }]);
  });

  it("pins nothing while no thread is open", () => {
    expect(barPin(0, -1, 3)).toBeNull();
    expect(barPin(2, -1, 3)).toBeNull();
  });
});

describe("what the pinned bars take of the scroll box (WCAG 2.2 2.4.11)", () => {
  it("is the stacked height of the bars pinned at the top and of those pinned at the bottom", () => {
    expect(pinnedSpace(1, 4)).toEqual({ top: 72, bottom: 72 });                // A, B up; C, D down
    expect(pinnedSpace(0, 3)).toEqual({ top: 36, bottom: 72 });
    expect(pinnedSpace(2, 3)).toEqual({ top: 108, bottom: 0 });
    expect(pinnedSpace(0, 1)).toEqual({ top: 36, bottom: 0 });
  });

  it("takes nothing while no thread is open", () => {
    expect(pinnedSpace(-1, 3)).toEqual({ top: 0, bottom: 0 });
    expect(pinnedSpace(-1, 0)).toEqual({ top: 0, bottom: 0 });
  });

  it("follows barPin's rule: each pinned bar adds its height, flush from its edge, whatever the open bar and count", () => {
    for (let n = 1; n <= 7; n++) {
      for (let open = -1; open < n; open++) {
        const pins = Array.from({ length: n }, (_, i) => barPin(i, open, n));
        const tops = pins.flatMap((p) => (p && "top" in p ? [p.top] : [])), bottoms = pins.flatMap((p) => (p && "bottom" in p ? [p.bottom] : []));
        expect(tops.sort((a, b) => a - b), `open ${open} of ${n}`).toEqual(tops.map((_, k) => k * BAR));       // stacked flush from the edge
        expect(bottoms.sort((a, b) => a - b), `open ${open} of ${n}`).toEqual(bottoms.map((_, k) => k * BAR));
        expect(pinnedSpace(open, n), `open ${open} of ${n}`).toEqual({ top: tops.length * BAR, bottom: bottoms.length * BAR });
      }
    }
  });
});

describe("the thread last opened, kept per review", () => {
  let store: Map<string, string>;
  beforeEach(() => {
    store = new Map();
    vi.stubGlobal("window", { localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) } });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("keeps it under ct.ws.<review id>.thread, apart from other reviews", () => {
    expect(loadThread(12)).toBeNull();
    saveThread(12, "T2");
    expect(store.get("ct.ws.12.thread")).toBe('"T2"');
    expect(loadThread(12)).toBe("T2");
    expect(loadThread(13)).toBeNull();
    saveThread(12, null);
    expect(loadThread(12)).toBeNull();
  });

  it("reads a stored value of the wrong shape as none", () => {
    store.set("ct.ws.12.thread", "42");
    expect(loadThread(12)).toBeNull();
  });
});
