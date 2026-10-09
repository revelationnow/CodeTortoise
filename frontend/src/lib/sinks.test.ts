import { afterEach, describe, expect, it, vi } from "vitest";
import type { Finding } from "../api";
import type { Annotation, Board, StoryDetail } from "../board/types";
import type { SinkHit } from "../reading/types";
import { quietBoard, quietFindings, quietStory, setShowSinks, showSinks, SHOW_KEY, sinkLine, whyText } from "./sinks";

afterEach(() => vi.unstubAllGlobals());

const hit = (label: string, why: SinkHit["why"], users = 0): SinkHit => ({ field: "N1", label, users, why, writers: [] });
const ann = (text: string, sink?: boolean) => ({ node: "N1", text, sink } as unknown as Annotation);
const board = (impacts: Annotation[]) => ({ impacts, nodes: [] } as unknown as Board);

describe("shared sinks", () => {
  it("says why each field is a sink", () => {
    expect([whyText(hit("a", "threshold", 312)), whyText(hit("a", "listed")), whyText(hit("a", "marked"))])
      .toEqual(["312 functions", "in tortoise.yaml", "marked"]);
  });

  it("writes the overview's line, one or many, hidden or shown", () => {
    expect(sinkLine([hit("log_t::buf", "threshold", 312), hit("stats_t::tx", "listed")], false))
      .toBe("2 shared sinks hidden: `log_t::buf` (312 functions), `stats_t::tx` (in tortoise.yaml)");
    expect(sinkLine([hit("Uart::errors", "marked")], true)).toBe("1 shared sink shown: `Uart::errors` (marked)");
  });

  it("leaves sink annotations and findings out unless shown", () => {
    const b = board([ann("writes x"), ann("writes buf", true)]);
    expect(quietBoard(b, false).impacts.map((a) => a.text)).toEqual(["writes x"]);
    expect(quietBoard(b, true)).toBe(b);
    expect(quietBoard(null, false)).toBe(null);
    const d = { board: b, graph: null } as unknown as StoryDetail;
    expect(quietStory(d, false).board.impacts).toHaveLength(1);
    expect(quietStory(d, false).graph).toBe(null);
    const fs = [{ id: "F1" }, { id: "F2", sink: true }] as Finding[];
    expect(quietFindings(fs, false).map((f) => f.id)).toEqual(["F1"]);
    expect(quietFindings(fs, true)).toBe(fs);
  });

  it("keeps the viewer's choice in the browser; hidden when storage is missing or throws", () => {
    const store = new Map<string, string>();
    vi.stubGlobal("window", { localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) } });
    expect(showSinks()).toBe(false);
    setShowSinks(true);
    expect(store.get(SHOW_KEY)).toBe("true");
    expect(showSinks()).toBe(true);
    vi.stubGlobal("window", { localStorage: { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("quota"); } } });
    expect(showSinks()).toBe(false);
    expect(() => setShowSinks(true)).not.toThrow();
    vi.unstubAllGlobals();
    expect(showSinks()).toBe(false);                 // no window at all (node)
  });
});
