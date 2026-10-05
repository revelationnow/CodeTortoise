import { describe, expect, it } from "vitest";
import type { Names } from "../api";
import { nameParts } from "./names";

const names: Names = {
  N9: { label: "uart_send", kind: "function", path: "//fixture/driver/uart.c", line: 11, story: "S1" },
  N16: { label: "Uart::errors", kind: "field", path: null, line: null, story: null },
};

describe("nameParts", () => {
  it("shows node ids as their names and finding ids as findings", () => {
    expect(nameParts("N9 writes N16; see F2.", names, ["F2"])).toEqual([
      { node: "N9", label: "uart_send" }, { text: " writes " }, { node: "N16", label: "Uart::errors" }, { text: "; see " },
      { finding: "F2" }, { text: "." }]);
  });

  it("keeps backticked code, naming ids inside it too", () => {
    expect(nameParts("`uart_send` (N9) and `N16`", names, [])).toEqual([
      { code: "uart_send" }, { text: " (" }, { node: "N9", label: "uart_send" }, { text: ") and " }, { node: "N16", label: "Uart::errors" }]);
  });

  it("never shows an id it cannot name", () => {
    expect(nameParts("N404 is gone", names, [])).toEqual([{ node: "N404", label: "a function" }, { text: " is gone" }]);
  });

  it("links only findings this review has; another F number stays text", () => {
    expect(nameParts("see F2 and F7", names, ["F2"])).toEqual([{ text: "see " }, { finding: "F2" }, { text: " and F7" }]);
    expect(nameParts("`F7` F7", names, [])).toEqual([{ code: "F7" }, { text: " F7" }]);
  });

  it("leaves words that only look like ids alone", () => {
    expect(nameParts("N12x and FN9", names, ["F9"])).toEqual([{ text: "N12x and FN9" }]);
  });
});
