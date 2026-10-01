import { describe, expect, it } from "vitest";
import type { Comment } from "../api";
import { lineAnchor, onLine } from "./anchors";

const c = (anchor: Record<string, unknown>) => ({ id: 1, parent_id: null, anchor_kind: "line", anchor } as Comment);

describe("line anchors", () => {
  it("match the new shape and M1's cumulative-diff shape", () => {
    expect(onLine(c(lineAnchor("//d/a.c", "new", 3)), "//d/a.c", "new", 3)).toBe(true);
    expect(onLine(c({ depot: "//d/a.c", cl: null, side: "new", line: 3 }), "//d/a.c", "new", 3)).toBe(true);
    expect(onLine(c({ depot: "//d/a.c", cl: 101, side: "new", line: 3 }), "//d/a.c", "new", 3)).toBe(false);
    expect(onLine(c({ depot: "//d/a.c", cl: 101, side: "new", line: 3 }), "//d/a.c", "new", 3, 101)).toBe(true);
    expect(onLine(c(lineAnchor("//d/a.c", "old", 3)), "//d/a.c", "new", 3)).toBe(false);
  });
});
