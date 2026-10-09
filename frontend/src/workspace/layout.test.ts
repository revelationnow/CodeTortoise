import { afterEach, describe, expect, test, vi } from "vitest";
import { CHECK_W, checkMax, HEAD_MIN, headMax, loadCheckW, loadHeadH } from "./layout";

function storage(items: Record<string, string>) {
  vi.stubGlobal("window", { localStorage: { getItem: (k: string) => items[k] ?? null, setItem: () => {} } });
}
afterEach(() => vi.unstubAllGlobals());

describe("the story's To check column", () => {
  test("takes up to 60% of the page and never less than its minimum", () => {
    expect(checkMax(1000)).toBe(600);
    expect(checkMax(300)).toBe(CHECK_W.min);
  });
  test("starts at its default and keeps a saved width", () => {
    storage({});
    expect(loadCheckW()).toBe(CHECK_W.def);
    storage({ "ct.ws.checkW": "480" });
    expect(loadCheckW()).toBe(480);
  });
  test("a saved width below the minimum or not a number falls back to the default", () => {
    storage({ "ct.ws.checkW": "90" });
    expect(loadCheckW()).toBe(CHECK_W.def);
    storage({ "ct.ws.checkW": "\"wide\"" });
    expect(loadCheckW()).toBe(CHECK_W.def);
  });
});

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
  test("storage that throws leaves both at their defaults", () => {
    vi.stubGlobal("window", { localStorage: { getItem: () => { throw new Error("blocked"); } } });
    expect(loadHeadH()).toBeNull();
    expect(loadCheckW()).toBe(CHECK_W.def);
  });
});
