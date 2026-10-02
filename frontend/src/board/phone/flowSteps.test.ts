import { describe, expect, it } from "vitest";
import { BOARD } from "./fixture";
import { flowSteps } from "./flowSteps";

const view = (i: number) => flowSteps(BOARD, BOARD.flows[i]).map((s) => [s.label, s.kind, s.marker, s.reason, s.hasCode]);

describe("flow steps", () => {
  it("lists a state flow from entry to landing with a reason per step", () => {
    expect(view(0)).toEqual([
      ["main", "plain", "1", "entry · app", true],
      ["logger_write", "plain", "2", "calls uart_send · checks != 0 — covers -2", true],
      ["uart_send", "chg", "Δ", "Δ modified +9 −1", true],
      ["Uart::errors", "field", "f", "field · new writer: uart_send · readers: uart_errors", true],
      ["uart_errors", "landing", "!", "reads Uart::errors — now also written by uart_send (line 17)", true],
    ]);
  });

  it("marks the landing of a contract flow even when it is not the last step", () => {
    expect(view(1)).toEqual([
      ["main", "plain", "1", "entry · app", true],
      ["logger_flush", "landing", "!", "result ignored — uart_send can now return -2", true],
      ["uart_send", "chg", "Δ", "Δ modified +9 −1", true],
    ]);
  });

  it("falls back to the flow's effect, and skips ids missing from the board", () => {
    const flow = { ...BOARD.flows[1], path: ["N6", "N404", "N1"], lands: "N1", fx_at: "N1" };
    expect(flowSteps(BOARD, flow).map((s) => [s.label, s.kind, s.reason, s.hasCode])).toEqual([
      ["main", "plain", "entry · app", true],
      ["hal_read", "landing", "logger_flush silently drops the new -2 result.", false],
    ]);
  });
});
