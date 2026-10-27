import { describe, expect, it } from "vitest";
import { menuAttention, menuItems, type MenuState } from "./reviewMenu";

const state = (over: Partial<MenuState> = {}): MenuState => ({
  drift: 0, notes: { failed: 0, degraded: 0 }, ai: null, reading: true, keys: true, owner: true, ready: true, strong: false, ...over });

describe("the review menu", () => {
  it("lists what moved out of the header, each only when it applies, in order", () => {
    expect(menuItems(state({ drift: 18, notes: { failed: 1, degraded: 2 }, ai: { used: 6, budget: 200 }, strong: true }))
      .map((i) => i.label)).toEqual(["Workspace drift · 18", "Stage notes · 3", "AI calls used · 6 of 200",
                                     "How to read this page", "Single-key shortcuts", "Re-run", "Re-run stories, fresh"]);
  });
  it("leaves out the AI line without an AI and the help without a reading", () => {
    expect(menuItems(state({ reading: false })).map((i) => i.id)).toEqual(["rerun"]);
  });
  it("offers Re-run to the owner of a finished review only, and fresh stories only with a strong model", () => {
    expect(menuItems(state({ owner: false, strong: true })).map((i) => i.id)).toEqual(["help", "keys"]);
    expect(menuItems(state({ ready: false, strong: true })).map((i) => i.id)).toEqual(["help", "keys"]);
    expect(menuItems(state()).map((i) => i.id)).toEqual(["help", "keys", "rerun"]);
  });
  it("offers the single-key shortcuts switch to anyone with a reading, right after the help, and says whether it is on", () => {
    expect(menuItems(state()).find((i) => i.id === "keys")).toEqual({ id: "keys", label: "Single-key shortcuts", checked: true });
    expect(menuItems(state({ keys: false })).find((i) => i.id === "keys")).toEqual({ id: "keys", label: "Single-key shortcuts", checked: false });
    const ids = menuItems(state({ strong: true, drift: 1 })).map((i) => i.id);
    expect(ids.indexOf("keys")).toBe(ids.indexOf("help") + 1);
    expect(menuItems(state({ owner: false, ready: false })).map((i) => i.id)).toEqual(["help", "keys"]);
    expect(menuItems(state({ reading: false })).map((i) => i.id)).not.toContain("keys");
    expect(menuItems(state()).filter((i) => i.id !== "keys").map((i) => i.checked)).toEqual([undefined, undefined]);   // a plain item is no checkbox
  });
  it("lights the dot for drift or a failed stage, not for a degraded one, and says why", () => {
    expect(menuAttention(state())).toBeNull();
    expect(menuAttention(state({ notes: { failed: 0, degraded: 2 } }))).toBeNull();
    expect(menuAttention(state({ drift: 3 }))).toBe("workspace drift");
    expect(menuAttention(state({ drift: 3, notes: { failed: 1, degraded: 0 } }))).toBe("workspace drift, a stage failed");
  });
});
