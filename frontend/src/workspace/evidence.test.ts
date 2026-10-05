import { describe, expect, it } from "vitest";
import { depotFor } from "./evidence";

const depots = ["//fixture/driver/uart.c", "//fixture/driver/uart.h", "//fixture/service/logger.c", "//other/service/logger.c.bak"];

describe("depotFor", () => {
  it("names the depot file a workspace path is, by the longest shared tail", () => {
    expect(depotFor("/home/u/ws/service/logger.c", depots)).toBe("//fixture/service/logger.c");
    expect(depotFor("/home/u/ws/driver/uart.h", depots)).toBe("//fixture/driver/uart.h");
  });

  it("passes depot paths through and gives up without a matching file name", () => {
    expect(depotFor("//fixture/driver/uart.c", depots)).toBe("//fixture/driver/uart.c");
    expect(depotFor("/home/u/ws/hal/regs.c", depots)).toBeNull();
  });

  it("refuses a tie it cannot break", () => {
    expect(depotFor("/ws/x/a.c", ["//p/y/a.c", "//q/z/a.c"])).toBeNull();
  });
});
