import { describe, expect, it } from "vitest";
import { counted, tidy } from "./tidy";

/** The same rules as backend/codetortoise/tidy.py (spec 2026-10-07-review-reading §12). */
describe("tidy", () => {
  it("turns Python reprs into lists and sentences", () => {
    expect(tidy("by layer: {'L1: hal': 1, 'L2: drv': 3}")).toBe("by layer: L1: hal (1), L2: drv (3)");
    expect(tidy("returns before: ['0']; after: ['-2', '0']")).toBe("returns before: 0; after: -2, 0");
    expect(tidy("returns before: []; after: [1]")).toBe("returns before: none; after: 1");
  });

  it("reads counts as words", () => {
    expect(tidy("regs.h: 1 change(s) reach 4 TU(s)")).toBe("regs.h: 1 change reaches 4 TUs");
    expect(tidy("affect 1 translation unit(s) across 2 layer(s).")).toBe("affect 1 translation unit across 2 layers.");
    expect(tidy("3 caller(s) must be re-checked: a, b, c")).toBe("3 callers must be re-checked: a, b, c");
  });

  it("gives a listed value the number of its list", () => {
    expect(tidy("uart_send: new return value(s) -2")).toBe("uart_send: new return value -2");
    expect(tidy("f: new return value(s) -2, -3")).toBe("f: new return values -2, -3");
  });

  it("reads arrows as arrows and leaves code alone", () => {
    expect(tidy("signature: `int f(int a[4])` -> `int f(int a[8])`")).toBe("signature: `int f(int a[4])` → `int f(int a[8])`");
    expect(tidy("writes Uart::errors via a -> b")).toBe("writes Uart::errors via a → b");
  });

  it("leaves anything else as it was", () => {
    for (const text of ["[medium] flush drops it", "{not a dict}", "a set {1, 2} of ids", "plain text", ""])
      expect(tidy(text)).toBe(text);
  });
});

describe("counted", () => {
  it("names a count with its noun and never shows an empty one", () => {
    expect(counted(0, "flow")).toBe("");
    expect(counted(1, "flow")).toBe("1 flow");
    expect(counted(3, "file")).toBe("3 files");
  });
});
