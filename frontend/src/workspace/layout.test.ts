import { afterEach, describe, expect, test, vi } from "vitest";
import { HEAD_MIN, headMax, loadHeadH } from "./layout";

function storage(items: Record<string, string>) {
  vi.stubGlobal("window", { localStorage: { getItem: (k: string) => items[k] ?? null, setItem: () => {} } });
}
afterEach(() => vi.unstubAllGlobals());

describe("the review header", () => {
  test("can be dragged between one line and half the window", () => {
    expect(HEAD_MIN).toBe(40);
    expect(headMax(900)).toBe(450);
    expect(headMax(60)).toBe(HEAD_MIN);
  });
  test("keeps its natural height until dragged, then the saved one", () => {
    storage({});
    expect(loadHeadH()).toBeNull();
    storage({ "ct.ws.headH": "120" });
    expect(loadHeadH()).toBe(120);
    storage({ "ct.ws.headH": "null" });
    expect(loadHeadH()).toBeNull();
  });
  test("a saved height that is too small or not a number is the natural height", () => {
    storage({ "ct.ws.headH": "12" });
    expect(loadHeadH()).toBeNull();
    storage({ "ct.ws.headH": "{}" });
    expect(loadHeadH()).toBeNull();
  });
  test("storage that throws leaves it at the natural height", () => {
    vi.stubGlobal("window", { localStorage: { getItem: () => { throw new Error("blocked"); } } });
    expect(loadHeadH()).toBeNull();
  });
});
