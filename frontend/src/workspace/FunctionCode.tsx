import { useMemo } from "react";
import CodeView from "../board/CodeView";
import { lineDiff, plainLines, sliceRange } from "../board/codeRows";
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
  const lines = useMemo(() => {
    if (isChange(src)) return sliceRange(lineDiff(src.before, src.after), lo - pad, hi + pad);
    if (src && "status" in src && src.status === "ok") return sliceRange(plainLines(src.file.text), lo - pad, hi + pad);
    return null;
  }, [src, lo, hi, pad]);
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
      {lines ? (
        <CodeView reviewId={d.id} path={node.path!} lines={lines} mode="unified" anns={board.impacts} comments={d.comments}
                  onComments={d.loadComments} />
      ) : src && "status" in src && src.status === "error" ? (
        <div className="bd-note error">{src.error} <button className="bd-ibtn" onClick={() => ws.sources.reload(node.path!)}>Retry</button></div>
      ) : <div className="bd-note">Fetching {node.path}…</div>}
      <div className="bd-fn-comments">
        <Comments reviewId={d.id} comments={d.comments} kind="function" anchor={{ key: node.key }} onChange={d.loadComments} compact />
      </div>
    </div>
  );
}
