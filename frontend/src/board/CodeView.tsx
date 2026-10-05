import { Fragment, memo, useMemo, useState } from "react";
import type { Comment } from "../api";
import Comments from "../components/Comments";
import FoldButton from "../components/FoldButton";
import { lineAnchor, onLine } from "../lib/anchors";
import { codeItems, lineKey, type Line, type Side, WINDOW, windowAround } from "./codeRows";
import { type Run, STEP } from "./fold";
import { tokens } from "./highlight";
import type { Annotation } from "./types";

interface Props {
  reviewId: number;
  path: string;
  lines: Line[];
  mode: "unified" | "split";
  anns: Annotation[];
  comments: Comment[];
  onComments: () => void;
  focus?: number | null;
  /** Full-file views: render big files as a window around the focus that grows on request. */
  windowed?: boolean;
  /** Changes view: only these runs are shown; folded runs offer to open (fold.ts). */
  runs?: Run[] | null;
  onExpand?: (run: Run, how: "up" | "down" | "all") => void;
  /** Comments made on one changelist's diff are anchored to it. */
  cl?: number | null;
}

const ICON = { warn: "⚠ ", ok: "✓ ", info: "ⓘ " } as const;

function Src({ text }: { text: string }) {
  return <>{tokens(text).map((t, i) => (t.cls ? <span key={i} className={`hl-${t.cls}`}>{t.text}</span> : t.text))}</>;
}

/** Code lines (diff or plain) with inline annotations and line comment threads; click a line to comment. */
function CodeView({ reviewId, path, lines, mode, anns, comments, onComments, focus, windowed, runs, onExpand, cl = null }: Props) {
  const [opened, setOpened] = useState<Set<string>>(new Set());
  const mine = useMemo(() => anns.filter((a) => a.path === path), [anns, path]);
  const threads = useMemo(() => {
    const keys = new Set(opened);
    for (const c of comments) {
      if (c.parent_id !== null || c.anchor_kind !== "line") continue;
      const side = c.anchor.side as Side, line = c.anchor.line as number;
      if (onLine(c, path, side, line, cl)) keys.add(lineKey(side, line));
    }
    return keys;
  }, [comments, opened, path]);
  const [extra, setExtra] = useState({ above: 0, below: 0, focus });
  const grow = extra.focus === focus ? extra : { above: 0, below: 0, focus };       // a new focus starts a new window
  const win = useMemo(() => (windowed && !runs ? windowAround(lines, mine, focus ?? null, grow) : { start: 0, end: lines.length }),
                      [windowed, runs, lines, mine, focus, grow]);
  // the changes view draws each shown run, and a control for each folded one
  type Block = { kind: "items"; items: ReturnType<typeof codeItems> } | { kind: "gap"; run: Run };
  const blocks = useMemo<Block[]>(() => (runs ?? [{ kind: "show", start: win.start, end: win.end } as Run]).map((r) =>
    r.kind === "gap" ? { kind: "gap", run: r } : { kind: "items", items: codeItems(lines.slice(r.start, r.end), mode, mine, threads) }),
  [runs, win.start, win.end, lines, mode, mine, threads]);
  const more = (side: "above" | "below", n: number) => setExtra({ ...grow, [side]: grow[side] + n });
  const open = (side: Side, no: number) => setOpened((s) => new Set(s).add(lineKey(side, no)));

  return (
    <div className="bd-code">
      {win.start > 0 && (
        <div className="bd-more-lines">
          <FoldButton icon="up" label={`Show ${Math.min(WINDOW, win.start)} more lines above`} onClick={() => more("above", WINDOW)} />
          <FoldButton icon="top" label={`Show all ${win.start} lines above`} onClick={() => more("above", Infinity)} />
          <span>{win.start} lines above</span>
        </div>
      )}
      {blocks.map((blk, bi) => blk.kind === "gap" ? (
        <div key={`g${bi}`} className="bd-gap">
          <FoldButton icon="down" label={`Show ${Math.min(STEP, blk.run.end - blk.run.start)} more lines, downward`} onClick={() => onExpand?.(blk.run, "down")} />
          <FoldButton icon="all" label={`Show all ${blk.run.end - blk.run.start} hidden lines`} onClick={() => onExpand?.(blk.run, "all")} />
          <FoldButton icon="up" label={`Show ${Math.min(STEP, blk.run.end - blk.run.start)} more lines, upward`} onClick={() => onExpand?.(blk.run, "up")} />
          <span>{blk.run.end - blk.run.start} lines hidden</span>
        </div>
      ) : blk.items.map((it, j) => {
        const i = `${bi}-${j}`;
        if (it.kind === "ann")
          return (
            <div key={i} className={`bd-ann ${it.ann.severity}`}>
              <span className="k">{ICON[it.ann.severity]}{it.ann.title}</span>{it.ann.text}
            </div>
          );
        if (it.kind === "thread")
          return (
            <div key={i} className="bd-thread" onPointerDown={(e) => e.stopPropagation()}>
              <Comments reviewId={reviewId} comments={comments} kind="line" anchor={lineAnchor(path, it.side, it.no, cl)}
                        match={(c) => onLine(c, path, it.side, it.no, cl)} onChange={onComments}
                        autoFocus={opened.has(lineKey(it.side, it.no))} />
            </div>
          );
        if (it.kind === "line") {
          const l = it.line;
          return (
            <div key={i} data-n={l.n ?? undefined} onClick={() => open(it.side, it.no)}
                 className={`bd-ln${l.t === "+" ? " a" : l.t === "-" ? " d" : ""}${it.hot ? " hot" : ""}${focus && l.n === focus ? " focus" : ""}`}>
              <span className="no">{l.n ?? l.o}</span><span className="sg">{l.t === "=" ? "" : l.t}</span>
              <span className="src"><Src text={l.text} /><span className="plus">＋ comment</span></span>
            </div>
          );
        }
        const { l, r } = it;
        return (
          <Fragment key={i}>
            <div data-n={r?.n ?? undefined} onClick={() => open(it.side, it.no)}
                 className={`bd-sbs${it.hot ? " hot" : ""}${focus && r?.n === focus ? " focus" : ""}`}>
              {l ? <><span className={`no l${l.t === "-" ? " d" : ""}`}>{l.o}</span><span className={`src l${l.t === "-" ? " d" : ""}`}><Src text={l.text} /></span></>
                 : <><span className="no empty" /><span className="src empty" /></>}
              {r ? <><span className={`no r${r.t === "+" ? " a" : ""}`}>{r.n}</span><span className={`src r${r.t === "+" ? " a" : ""}`}><Src text={r.text} /><span className="plus">＋ comment</span></span></>
                 : <><span className="no empty" /><span className="src empty"><span className="plus">＋ comment</span></span></>}
            </div>
          </Fragment>
        );
      }))}
      {win.end < lines.length && (
        <div className="bd-more-lines">
          <FoldButton icon="down" label={`Show ${Math.min(WINDOW, lines.length - win.end)} more lines below`} onClick={() => more("below", WINDOW)} />
          <FoldButton icon="bottom" label={`Show all ${lines.length - win.end} lines below`} onClick={() => more("below", Infinity)} />
          <span>{lines.length - win.end} lines below</span>
        </div>
      )}
    </div>
  );
}

export default memo(CodeView);
