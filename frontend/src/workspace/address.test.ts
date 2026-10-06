import { describe, expect, it } from "vitest";
import { type Address, href, placeKey, readAddress, samePlace } from "./address";

const q = (s: string) => new URLSearchParams(s);

describe("readAddress", () => {
  it("reads each kind of place", () => {
    expect(readAddress("", q("")).place).toEqual({ kind: "whole" });
    expect(readAddress("", q("view=graph")).place).toEqual({ kind: "whole", view: "graph" });
    expect(readAddress("/s/S1", q("")).place).toEqual({ kind: "story", sid: "S1", view: "steps" });
    expect(readAddress("/s/S1", q("view=graph")).place).toEqual({ kind: "story", sid: "S1", view: "graph" });
    expect(readAddress("/f/F2", q("")).place).toEqual({ kind: "finding", fid: "F2" });
    expect(readAddress("/cl/101", q("")).place).toEqual({ kind: "cl", cl: 101 });
    expect(readAddress("/c/C3/", q("")).place).toEqual({ kind: "cluster", cid: "C3" });
  });

  it("reads the flow, what the detail panel shows and its tab", () => {
    const a = readAddress("/s/S1", q("view=graph&flow=2&open=N9&tab=neighbours"));
    expect([a.flow, a.open, a.tab]).toEqual([2, { node: "N9" }, "neighbours"]);
    expect(readAddress("", q("open=file://fixture/driver/uart.c:17")).open).toEqual({ file: "//fixture/driver/uart.c", line: 17 });
    expect(readAddress("", q("open=file://fixture/driver/uart.c")).open).toEqual({ file: "//fixture/driver/uart.c", line: null });
    expect(readAddress("", q("open=file://d/a.c:0")).open).toEqual({ file: "//d/a.c", line: null });   // lines start at 1
  });

  it("falls back on anything it cannot read", () => {
    const a = readAddress("/nowhere/x", q("flow=0&tab=sideways&view=map&open=file:"));
    expect(a).toEqual({ place: { kind: "unknown", path: "/nowhere/x" }, flow: null, open: null, tab: "diff" });
    expect(readAddress("/cl/abc", q("")).place).toEqual({ kind: "unknown", path: "/cl/abc" });
  });
});

describe("href", () => {
  it("writes an address back, leaving out defaults", () => {
    const a: Address = { place: { kind: "story", sid: "S1", view: "graph" }, flow: 2, open: { node: "N9" }, tab: "neighbours" };
    expect(href("/w/7", a)).toBe("/w/7/s/S1?view=graph&flow=2&open=N9&tab=neighbours");
    expect(href("/w/7", { place: { kind: "whole" }, flow: null, open: null, tab: "diff" })).toBe("/w/7");
    expect(href("/w/7", { place: { kind: "cl", cl: 101 }, flow: null, open: { file: "//d/a.c", line: 4 }, tab: "diff" }))
      .toBe("/w/7/cl/101?open=file%3A%2F%2Fd%2Fa.c%3A4");
  });

  it("round-trips every place", () => {
    for (const [path, view] of [["", ""], ["", "graph"], ["/s/S2", "graph"], ["/f/F1", ""], ["/cl/102", ""], ["/c/C1", ""]]) {
      const a = readAddress(path, q(`flow=3&open=file://d/x.h&view=${view}`));
      const [p, s] = href("/r/1", a).slice("/r/1".length).split("?");
      expect(readAddress(p, q(s ?? ""))).toEqual(a);
    }
  });
});

describe("a story lit on a map", () => {
  it("rides on the whole graph and a part, and nowhere else", () => {
    const q = (s: string) => new URLSearchParams(s);
    expect(readAddress("/", q("view=graph&story=S2")).story).toBe("S2");
    expect(href("/r/7", { place: { kind: "whole", view: "graph" }, flow: null, open: null, tab: "diff", story: "S2" })).toBe("/r/7?view=graph&story=S2");
    expect(href("/r/7", { place: { kind: "cluster", cid: "C1" }, flow: null, open: null, tab: "diff", story: "S2" })).toBe("/r/7/c/C1?story=S2");
    expect(href("/r/7", { place: { kind: "story", sid: "S2", view: "steps" }, flow: null, open: null, tab: "diff", story: "S2" })).toBe("/r/7/s/S2");
  });
});

describe("places", () => {
  it("have a key per item and compare by item, not view", () => {
    expect(placeKey({ kind: "story", sid: "S1", view: "graph" })).toBe("s:S1");
    expect(placeKey({ kind: "whole" })).toBe("whole");
    expect(placeKey({ kind: "whole", view: "graph" })).toBe("whole");
    expect(samePlace({ kind: "story", sid: "S1", view: "graph" }, { kind: "story", sid: "S1", view: "steps" })).toBe(true);
    expect(samePlace({ kind: "finding", fid: "F1" }, { kind: "finding", fid: "F2" })).toBe(false);
  });
});
