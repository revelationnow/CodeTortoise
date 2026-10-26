import { describe, expect, it } from "vitest";
import { menuAttention, menuItems, type MenuState } from "./reviewMenu";

const state = (over: Partial<MenuState> = {}): MenuState => ({
  drift: 0, notes: { failed: 0, degraded: 0 }, ai: null, reading: true, owner: true, ready: true, strong: false, ...over });

describe("the review menu", () => {
  it("lists what moved out of the header, each only when it applies, in order", () => {
    expect(menuItems(state({ drift: 18, notes: { failed: 1, degraded: 2 }, ai: { used: 6, budget: 200 }, strong: true }))
      .map((i) => i.label)).toEqual(["Workspace drift · 18", "Stage notes · 3", "AI calls used · 6 of 200",
                                     "How to read this page", "Re-run", "Re-run stories, fresh"]);
  });
  it("leaves out the AI line without an AI and the help without a reading", () => {
    expect(menuItems(state({ reading: false })).map((i) => i.id)).toEqual(["rerun"]);
  });
  it("offers Re-run to the owner of a finished review only, and fresh stories only with a strong model", () => {
    expect(menuItems(state({ owner: false, strong: true })).map((i) => i.id)).toEqual(["help"]);
    expect(menuItems(state({ ready: false, strong: true })).map((i) => i.id)).toEqual(["help"]);
    expect(menuItems(state()).map((i) => i.id)).toEqual(["help", "rerun"]);
  });
  it("lights the dot for drift or a failed stage, not for a degraded one, and says why", () => {
    expect(menuAttention(state())).toBeNull();
    expect(menuAttention(state({ notes: { failed: 0, degraded: 2 } }))).toBeNull();
    expect(menuAttention(state({ drift: 3 }))).toBe("workspace drift");
    expect(menuAttention(state({ drift: 3, notes: { failed: 1, degraded: 0 } }))).toBe("workspace drift, a stage failed");
  });
});
