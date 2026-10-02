import { describe, expect, it } from "vitest";
import { BOARD } from "./phone/fixture";
import { sideEffectFiles } from "./sideEffects";

describe("files with side effects", () => {
  it("groups affected unchanged functions by directory, marking files that are also changed", () => {
    const dirs = sideEffectFiles(BOARD);
    expect(dirs.map((d) => d.dir)).toEqual(["driver", "service"]);
    const [uart] = dirs[0].files, [logger] = dirs[1].files;
    expect([uart.name, uart.path, uart.alsoChanged, uart.warn]).toEqual(["uart.c", "//fixture/driver/uart.c", true, 3]);
    expect(uart.fns.map((f) => [f.label, f.line, f.severity, f.landing])).toEqual([
      ["uart_init", 7, "warn", false], ["uart_errors", 29, "warn", true]]);
    expect([logger.name, logger.alsoChanged, logger.warn]).toEqual(["logger.c", false, 1]);
    expect(logger.fns.map((f) => [f.label, f.line, f.text])).toEqual([
      ["logger_write", 12, "checks != 0 — covers -2"], ["logger_flush", 21, "result ignored — uart_send can now return -2"]]);
  });

  it("leaves out changed functions, fields and annotations without a path", () => {
    const labels = sideEffectFiles(BOARD).flatMap((d) => d.files.flatMap((f) => f.fns.map((x) => x.label)));
    expect(labels).not.toContain("uart_send");
    expect(labels).not.toContain("Uart::errors");
    const none = { ...BOARD, impacts: BOARD.impacts.map((a) => ({ ...a, path: null })) };
    expect(sideEffectFiles(none)).toEqual([]);
  });
});
