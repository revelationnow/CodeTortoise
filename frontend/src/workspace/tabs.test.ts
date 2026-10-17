import { describe, expect, it } from "vitest";
import type { Item } from "./address";
import { addTab, closeTab, MAX_TABS, openKey, tabLabel } from "./tabs";

const f = (id: string): Item => ({ finding: id });
const file = (p: string, line: number | null = null): Item => ({ file: p, line });

describe("addTab", () => {
  it("adds new items last and keeps an open item's place, taking its new line", () => {
    let t = addTab([], f("F1"));
    t = addTab(t, file("//d/a.c", 3));
    t = addTab(t, { node: "N2" });
    t = addTab(t, file("//d/a.c", 9));
    expect(t).toEqual([f("F1"), file("//d/a.c", 9), { node: "N2" }]);
  });

  it("returns the same list when the item is already there as it is", () => {
    const t = [f("F1")];
    expect(addTab(t, f("F1"))).toBe(t);
  });

  it("keeps at most 8, dropping the oldest", () => {
    let t: Item[] = [];
    for (let i = 1; i <= 9; i++) t = addTab(t, f(`F${i}`));
    expect(t).toHaveLength(MAX_TABS);
    expect(t.map(openKey)).toEqual(["f:F2", "f:F3", "f:F4", "f:F5", "f:F6", "f:F7", "f:F8", "f:F9"]);
  });
});

describe("closeTab", () => {
  const t = [f("F1"), f("F2"), f("F3")];

  it("closing a tab that is not active leaves the panel as it is", () => {
    expect(closeTab(t, f("F1"), f("F3"))).toEqual({ tabs: [f("F2"), f("F3")], next: undefined });
  });

  it("closing the active tab activates its left neighbour, or the right one when it was first", () => {
    expect(closeTab(t, f("F2"), f("F2")).next).toEqual(f("F1"));
    expect(closeTab(t, f("F1"), f("F1")).next).toEqual(f("F2"));
  });

  it("closing the last tab closes the panel", () => {
    expect(closeTab([f("F1")], f("F1"), f("F1"))).toEqual({ tabs: [], next: null });
  });
});

describe("tabLabel", () => {
  it("names a finding by its id, a file by its name and a function by its name", () => {
    const names = { N2: { label: "uart_send", kind: "function", path: null, line: null, story: null } };
    expect([tabLabel(f("F4"), names), tabLabel(file("//d/driver/uart.c", 4), names), tabLabel({ node: "N2" }, names)])
      .toEqual(["F4", "uart.c", "uart_send"]);
  });
});

describe("a cause's tab", () => {
  const c = { id: "c01", kind: "reader" as const, thread: null, story: null, text: "5 places read `UartDev::errors`, which `N9` now writes",
              places: ["a"], flows: [], finding: null, change: null };
  it("is one tab whatever place it is at, named by its line without node ids", () => {
    const t = addTab(addTab([], { cause: "c01", at: 1 }), { cause: "c01", at: 4 });
    expect(t).toEqual([{ cause: "c01", at: 4 }]);
    expect(openKey(t[0])).toBe("c:c01");
    const names = { N9: { label: "uart_a1", kind: "function", path: null, line: null, story: null } };
    expect(tabLabel(t[0], names, [c])).toBe("5 places read UartDev::errors, which…");
    expect(tabLabel({ cause: "gone", at: 1 }, names, [c])).toBe("Check");
  });
});
