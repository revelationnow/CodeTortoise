import { describe, expect, it } from "vitest";
import { type Action, type BoardState, initialState, reduce } from "./reducer";

const run = (...actions: Action[]) => actions.reduce(reduce, initialState());
const open = (path: string, line?: number): Action => ({ t: "viewer.open", path, line, wide: true });

describe("cards", () => {
  it("node click opens a card and brings it to the front, never closes it", () => {
    let s = run({ t: "card.open", id: "N1" }, { t: "card.open", id: "N2" });
    expect(s.z).toEqual(["N1", "N2"]);
    s = reduce(s, { t: "card.open", id: "N1" });
    expect(Object.keys(s.cards).sort()).toEqual(["N1", "N2"]);
    expect(s.z).toEqual(["N2", "N1"]);
  });

  it("only close removes a card; close all removes every card", () => {
    let s = run({ t: "card.open", id: "N1" }, { t: "card.open", id: "N2" }, { t: "card.close", id: "N1" });
    expect(s.cards).toEqual({ N2: { collapsed: false } });
    expect(s.z).toEqual(["N2"]);
    s = reduce(s, { t: "card.closeAll" });
    expect(s.cards).toEqual({});
    expect(s.z).toEqual([]);
  });

  it("step chips toggle a card open and closed", () => {
    let s = run({ t: "card.toggle", id: "N1" });
    expect(s.cards.N1).toEqual({ collapsed: false });
    s = reduce(s, { t: "card.toggle", id: "N1" });
    expect(s.cards.N1).toBeUndefined();
  });

  it("a dragged card keeps its offset until unpinned", () => {
    let s = run({ t: "card.open", id: "N1" }, { t: "card.move", id: "N1", offset: { x: 40, y: -10 } });
    expect(s.cards.N1.offset).toEqual({ x: 40, y: -10 });
    s = reduce(s, { t: "card.unpin", id: "N1" });
    expect(s.cards.N1).toEqual({ collapsed: false });
  });

  it("front and expand ignore cards that are not open", () => {
    const s = initialState();
    expect(reduce(s, { t: "card.front", id: "N9" })).toBe(s);
    expect(reduce(s, { t: "card.expand", id: "N9" })).toBe(s);
  });
});

describe("viewer", () => {
  it("opening the viewer collapses every card and closing it restores them exactly", () => {
    let s = run({ t: "card.open", id: "N1" }, { t: "card.open", id: "N2" });
    s = reduce(s, open("//d/a.c", 10));
    expect(s.cards.N1.collapsed && s.cards.N2.collapsed).toBe(true);
    s = reduce(s, { t: "card.expand", id: "N1" });       // a pill clicked while the viewer is open
    s = reduce(s, { t: "card.open", id: "N3" });         // a new card starts as a pill
    expect(s.cards.N3.collapsed).toBe(true);
    s = reduce(s, { t: "viewer.closeAll" });
    expect(s.cards).toEqual({ N1: { collapsed: false }, N2: { collapsed: false }, N3: { collapsed: true } });
    expect(s.viewer.files).toEqual([]);
    expect(s.viewer.snapshot).toBeNull();
  });

  it("closing a card while the viewer is open drops it from the snapshot", () => {
    let s = run({ t: "card.open", id: "N1" }, open("//d/a.c"), { t: "card.close", id: "N1" }, { t: "viewer.closeAll" });
    expect(s.cards).toEqual({});
    s = run({ t: "card.open", id: "N1" }, open("//d/a.c"), { t: "card.closeAll" }, { t: "card.open", id: "N2" },
            { t: "viewer.closeAll" });
    expect(s.cards).toEqual({ N2: { collapsed: true } });
  });

  it("files stack newest first; reopening moves a file to the top and expands it", () => {
    let s = run(open("//d/a.c"), open("//d/b.c"), { t: "viewer.toggle", path: "//d/a.c" });
    expect(s.viewer.files).toEqual(["//d/b.c", "//d/a.c"]);
    expect(s.viewer.collapsed).toEqual(["//d/a.c"]);
    s = reduce(s, open("//d/a.c", 7));
    expect(s.viewer.files).toEqual(["//d/a.c", "//d/b.c"]);
    expect(s.viewer.collapsed).toEqual([]);
    expect(s.viewer.reveal).toEqual({ path: "//d/a.c", line: 7, seq: 3 });
  });

  it("expand all, collapse all, mode and per-file close", () => {
    let s = run(open("//d/a.c"), open("//d/b.c"), { t: "viewer.collapseAll" });
    expect(s.viewer.collapsed.sort()).toEqual(["//d/a.c", "//d/b.c"]);
    s = reduce(s, { t: "viewer.expandAll" });
    expect(s.viewer.collapsed).toEqual([]);
    expect(s.viewer.mode).toBe("split");
    s = reduce(s, { t: "viewer.mode", mode: "unified" });
    s = reduce(s, { t: "viewer.close", path: "//d/b.c" });
    expect(s.viewer.files).toEqual(["//d/a.c"]);
    s = reduce(s, { t: "viewer.close", path: "//d/a.c" });
    expect(s.viewer.files).toEqual([]);
    expect(s.viewer.mode).toBe("unified");               // kept for the next open
  });

  it("narrow screens start stacked", () => {
    const s = reduce(initialState(), { t: "viewer.open", path: "//d/a.c", wide: false });
    expect(s.viewer.mode).toBe("unified");
  });
});

describe("board", () => {
  it("selecting a flow returns to flows mode", () => {
    const s = run({ t: "mode", mode: "graph" }, { t: "flow", i: 2 });
    expect([s.mode, s.flow]).toEqual(["flows", 2]);
  });

  it("node moves are remembered until reset", () => {
    let s: BoardState = run({ t: "node.move", id: "N1", x: 120 }, { t: "node.move", id: "N2", x: -40 });
    expect(s.moved).toEqual({ N1: 120, N2: -40 });
    s = reduce(s, { t: "layout.reset" });
    expect(s.moved).toEqual({});
  });

  it("lens, pan and the change panel", () => {
    const s = run({ t: "lens", lens: 4 }, { t: "pan", panX: 5, panY: 6 }, { t: "about.toggle" });
    expect(s.view).toEqual({ panX: 5, panY: 6, lens: 4 });
    expect(s.about).toBe(true);
    expect(reduce(s, { t: "about.toggle", open: false }).about).toBe(false);
  });
});
