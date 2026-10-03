import { describe, expect, it } from "vitest";
import { type Line } from "./codeRows";
import { expandRange, foldRuns, revealRange, STEP } from "./fold";

const L = (t: Line["t"], k: number): Line => ({ t, o: t === "+" ? null : k, n: t === "-" ? null : k, text: `l${k}` });
// 60 lines, one change at index 30 (a deleted and an added line)
const lines: Line[] = [...Array.from({ length: 30 }, (_, i) => L("=", i + 1)), L("-", 31), L("+", 31),
                       ...Array.from({ length: 28 }, (_, i) => L("=", i + 32))];

describe("folding a diff (changes view)", () => {
  it("shows changed lines with 3 lines of context and folds the rest", () => {
    expect(foldRuns(lines, [])).toEqual([
      { kind: "gap", start: 0, end: 27 }, { kind: "show", start: 27, end: 35 }, { kind: "gap", start: 35, end: 60 }]);
  });

  it("grows a gap 15 lines at a time from either edge, or all at once", () => {
    const [top] = foldRuns(lines, []);
    expect(STEP).toBe(15);
    expect(expandRange(top, "up")).toEqual([12, 27]);                 // ▲: lines just above the change
    expect(expandRange(top, "down")).toEqual([0, 15]);                // ▼: lines from the top of the gap
    expect(expandRange(top, "all")).toEqual([0, 27]);
    expect(foldRuns(lines, [[12, 27]])).toEqual([
      { kind: "gap", start: 0, end: 12 }, { kind: "show", start: 12, end: 35 }, { kind: "gap", start: 35, end: 60 }]);
  });

  it("reveals a hidden line with 15 lines around it, and leaves no tiny gaps", () => {
    expect(revealRange(lines, 50)).toEqual([35, 66]);                 // new-side line 50 is index 50
    expect(foldRuns(lines, [revealRange(lines, 50)!])).toEqual([
      { kind: "gap", start: 0, end: 27 }, { kind: "show", start: 27, end: 60 }]);
    expect(revealRange(lines, 999)).toBeNull();
    const near = [...Array.from({ length: 5 }, (_, i) => L("=", i + 1)), L("+", 6), L("=", 7)];
    expect(foldRuns(near, [])).toEqual([{ kind: "show", start: 0, end: 7 }]);   // a 2-line gap isn't worth folding
  });

  it("a file with no changes is one gap", () => {
    expect(foldRuns(lines.filter((l) => l.t === "="), [])).toEqual([{ kind: "gap", start: 0, end: 58 }]);
  });
});

describe("lines that carry notes or comments", () => {
  it("stay visible with their context, like changes", () => {
    // index 5 kept: 2..8 shown; the 2-line run above it is too short to fold
    expect(foldRuns(lines, [], new Set([5]))).toEqual([
      { kind: "show", start: 0, end: 9 }, { kind: "gap", start: 9, end: 27 }, { kind: "show", start: 27, end: 35 },
      { kind: "gap", start: 35, end: 60 }]);
  });
});
