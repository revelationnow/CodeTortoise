/** Shared sinks (spec 2026-10-09-shared-sinks §5): fields so many functions touch that the review hides writes to them.
 * Whether to show them is each viewer's own, kept in the browser; hidden is the default. */
import type { Finding } from "../api";
import { load, save } from "../board/prefs";
import type { Board, StoryDetail } from "../board/types";
import type { SinkHit } from "../reading/types";

export const SHOW_KEY = "ct.sinks.show";
export const showSinks = (): boolean => load<unknown>(SHOW_KEY, false) === true;
export const setShowSinks = (on: boolean): void => save(SHOW_KEY, on);

export function whyText(s: { why: SinkHit["why"]; users: number }): string {
  return s.why === "threshold" ? `${s.users} functions` : s.why === "listed" ? "in tortoise.yaml" : "marked";
}

/** "2 shared sinks hidden: `log_t::buf` (312 functions), `stats_t::tx` (in tortoise.yaml)" */
export function sinkLine(hits: SinkHit[], shown: boolean): string {
  const n = hits.length;
  return `${n} shared sink${n === 1 ? "" : "s"} ${shown ? "shown" : "hidden"}: `
    + hits.map((h) => `\`${h.label}\` (${whyText(h)})`).join(", ");
}

export function quietBoard<B extends Board | null>(b: B, show: boolean): B {
  return !b || show ? b : { ...b, impacts: b.impacts.filter((a) => !a.sink) };
}

export function quietStory(d: StoryDetail, show: boolean): StoryDetail {
  return show ? d : { ...d, board: quietBoard(d.board, false), graph: quietBoard(d.graph, false) };
}

export const quietFindings = (fs: Finding[], show: boolean): Finding[] => (show ? fs : fs.filter((f) => !f.sink));
