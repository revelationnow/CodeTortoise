import { useEffect, useMemo, useRef, useState } from "react";
import CodeView from "../board/CodeView";
import { lineDiff, plainLines } from "../board/codeRows";
import { expandRange, functionView, type Range, STEP } from "../board/fold";
import type { Board, BoardNode } from "../board/types";
import { isChange, useEnsureSource } from "../board/useSources";
import Comments from "../components/Comments";
import { useWs } from "./context";

/** A function's code slice with its effects (changed) or what it touches (context), and its comments: the detail
 * panel's Diff tab for a node (spec 2026-10-04-review-workspace §3.7; was the floating card's body). */
export default function FunctionCode({ node, board }: { node: BoardNode; board: Board }) {
  const ws = useWs(), d = ws.data;
  const src = useEnsureSource(node.path, ws.sources);
  const [lo, hi] = node.range ?? [0, 0];
  const pad = node.kind === "field" || node.kind === "struct" ? 4 : 0;
  const [more, setMore] = useState({ above: 0, below: 0 });
  const [shown, setShown] = useState<Range[]>([]);
  useEffect(() => { setMore({ above: 0, below: 0 }); setShown([]); }, [node.id]);
  const view = useMemo(() => {
    const all = isChange(src) ? lineDiff(src.before, src.after)
      : src && "status" in src && src.status === "ok" ? plainLines(src.file.text) : null;
    return all && functionView(all, lo - pad, hi + pad, more, shown, isChange(src));
  }, [src, lo, hi, pad, more, shown]);
  const lines = view?.lines ?? null;
  const box = useRef<HTMLDivElement>(null);
  const changed = !!view?.runs;
  useEffect(() => {                                 // a changed function opens on its first change
    if (!changed) return;
    const id = window.requestAnimationFrame(() =>
      box.current?.querySelector(".bd-ln.a, .bd-ln.d, .bd-sbs .src.a, .bd-sbs .src.d")?.scrollIntoView({ block: "center" }));
    return () => window.cancelAnimationFrame(id);
  }, [changed, node.id]);
  const grow = (side: "above" | "below") => setMore((m) => ({ ...m, [side]: m[side] + STEP }));
  const effects = board.impacts.filter((a) => a.node === node.id && a.severity === "warn");
  const touches = useMemo(() => {
    const own = board.impacts.find((a) => a.node === node.id);
    if (own) return own.text;
    const changed = new Map(board.nodes.filter((n) => n.change).map((n) => [n.id, n.label]));
    const e = board.edges.find((e) => e.src === node.id && changed.has(e.dst));
    return e ? `${e.kind === "call" || e.kind === "virtual" ? "calls" : e.kind} ${changed.get(e.dst)} (changed)` : "context";
  }, [board, node.id]);
  return (
    <div className="ws-fn">
      {node.change ? (
        effects.length > 0 && <div className="effects">{effects.map((a, i) => <div key={i}><span className="ico">⚠</span>{a.text}</div>)}</div>
      ) : <div className="fetched">Unchanged · {touches}</div>}
      {lines && view ? (
        <div className="ws-fn-code" ref={box}>
          {view.above > 0 && (
            <div className="bd-more-lines">⋯ {view.above} lines above the function
              <button onClick={() => grow("above")}>Show {Math.min(STEP, view.above)} more</button></div>
          )}
          <CodeView reviewId={d.id} path={node.path!} lines={lines} mode="unified" anns={board.impacts} comments={d.comments}
                    onComments={d.loadComments} runs={view.runs}
                    onExpand={(run, how) => setShown((r) => [...r, expandRange(run, how)])} />
          {view.below > 0 && (
            <div className="bd-more-lines">⋯ {view.below} lines below the function
              <button onClick={() => grow("below")}>Show {Math.min(STEP, view.below)} more</button></div>
          )}
        </div>
      ) : src && "status" in src && src.status === "error" ? (
        <div className="bd-note error">{src.error} <button className="bd-ibtn" onClick={() => ws.sources.reload(node.path!)}>Retry</button></div>
      ) : <div className="bd-note">Fetching {node.path}…</div>}
      <div className="bd-fn-comments">
        <Comments reviewId={d.id} comments={d.comments} kind="function" anchor={{ key: node.key }} onChange={d.loadComments} compact />
      </div>
    </div>
  );
}
