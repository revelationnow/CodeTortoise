/** A hand-built board shaped like the uart fixture review (CLs 101+102), for phone unit tests. */
import type { Annotation, Board, BoardNode } from "../types";

const n = (id: string, label: string, layer: number, extra: Partial<BoardNode> = {}): BoardNode => ({
  id, key: id, label, kind: "function", layer, path: "//fixture/x.c", local: "/w/x.c", range: [1, 5], change: null, x: 0, warn: 0,
  ...extra,
});
const ann = (node: string, path: string, line: number, severity: Annotation["severity"], text: string, landing = false): Annotation => ({
  node, path, line, side: "new", severity, channel: "state", title: "State", text, finding: "F1", cause: "N9", landing,
});

export const BOARD: Board = {
  nodes: [
    n("N6", "main", 4, { path: "//fixture/app/main.c" }),
    n("N5", "logger_write", 3, { path: "//fixture/service/logger.c", range: [10, 17] }),
    n("N3", "logger_flush", 3, { path: "//fixture/service/logger.c", range: [19, 22] }),
    n("N9", "uart_send", 2, { path: "//fixture/driver/uart.c", range: [11, 25], change: { kind: "modified", add: 9, rem: 1 } }),
    n("N16", "Uart::errors", 2, { kind: "field", path: "//fixture/driver/uart.h", range: [15, 15] }),
    n("N7", "uart_errors", 2, { path: "//fixture/driver/uart.c", range: [27, 30] }),
    n("N8", "uart_init", 2, { path: "//fixture/driver/uart.c", range: [3, 9] }),
    n("N2", "hal_write", 1, { path: "//fixture/hal/regs.c", change: { kind: "signature", add: 1, rem: 1 } }),
    n("N1", "hal_read", 1, { path: null, range: null }),
  ],
  edges: [],
  flows: [
    { id: "FL1", path: ["N6", "N5", "N9", "N16", "N7"], tag: "state", lands: "N7", fx_at: null, severity: "high", findings: ["F1"],
      text: "main → logger_write → uart_send → Uart::errors → uart_errors", title: "uart_errors sees a new writer of Uart::errors",
      what: "main reaches uart_send…", effect: "uart_errors now sees…", check: "whether…", what_source: "template" },
    { id: "FL2", path: ["N6", "N3", "N9"], tag: "contract", lands: "N3", fx_at: "N3", severity: "medium", findings: ["F5"],
      text: "main → logger_flush → uart_send ⟶ -2 ignored", title: "logger_flush ignores -2",
      what: "…", effect: "logger_flush silently drops the new -2 result.", check: "…", what_source: "template" },
  ],
  impacts: [
    ann("N9", "//fixture/driver/uart.c", 17, "warn", "writes Uart::errors through alias `err`"),
    ann("N5", "//fixture/service/logger.c", 12, "ok", "checks != 0 — covers -2"),
    ann("N3", "//fixture/service/logger.c", 21, "warn", "result ignored — uart_send can now return -2", true),
    ann("N7", "//fixture/driver/uart.c", 29, "warn", "reads Uart::errors — now also written by uart_send (line 17)", true),
    ann("N8", "//fixture/driver/uart.c", 7, "warn", "writes Uart::errors — now also written by uart_send (line 17)"),
    ann("N8", "//fixture/driver/uart.c", 8, "warn", "calls hal_write, whose signature changed"),
    ann("N16", "//fixture/driver/uart.h", 15, "warn", "new writer: uart_send · readers: uart_errors"),
  ],
  layers: [{ level: 4, name: "app" }, { level: 3, name: "service" }, { level: 2, name: "driver" }, { level: 1, name: "hal" }],
  about: { intent: "", intent_source: "template", why: [], cls: [],
           tree: [{ dir: "driver", files: [{ path: "//fixture/driver/uart.c", name: "uart.c", action: "edit", cls: [101], add: 9, rem: 1 },
                                          { path: "//fixture/driver/uart.h", name: "uart.h", action: "edit", cls: [102], add: 1, rem: 0 }] },
                  { dir: "hal", files: [{ path: "//fixture/hal/regs.c", name: "regs.c", action: "edit", cls: [102], add: 1, rem: 1 }] }],
           drift: [] },
  hidden_nodes: 0,
};
