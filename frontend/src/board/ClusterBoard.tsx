import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, type Comment, type FileChange } from "../api";
import Board from "./Board";
import { addExpansion, stepCluster } from "./overview";
import { type BoardKey, keys, loadExpand, save } from "./prefs";
import type { Board as BoardModel, Overview } from "./types";

interface Props {
  reviewId: number;
  ov: Overview;
  cid: string;
  files: FileChange[];
  comments: Comment[];
  onComments: () => void;
  risk: string | null;
  head: (extra: ReactNode) => ReactNode;
  /** Bumped when an AI explanation finished: the board is fetched again. */
  reload: number;
}

/** One cluster's board in a split review (spec 2026-10-03-large-change-boards §5): breadcrumb and ‹ ›, visitors
 * linking to their clusters, "+N callers" expansions kept in the page address (and remembered per cluster). */
export default function ClusterBoard({ reviewId, ov, cid, files, comments, onComments, risk, head, reload }: Props) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const prefKey = `${reviewId}.${cid}`;
  const { expand, expansion } = useExpansion(prefKey);
  const [board, setBoard] = useState<BoardModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api.board(reviewId, cid, expand).then((b) => { if (live) { setBoard(b); setError(null); } })
      .catch((e) => { if (live) setError(e instanceof ApiError && e.status === 404 ? e.message : String(e.message ?? e)); });
    return () => { live = false; };
  }, [reviewId, cid, expand, reload]);
  const focus = params.get("node");
  useEffect(() => {                                       // a node this board doesn't show: open the board that does
    if (!board || !focus || board.nodes.some((n) => n.id === focus)) return;
    let live = true;
    api.locate(reviewId, { node: focus }).then(({ cluster }) => {
      if (live && cluster && cluster !== cid) navigate(`/r/${reviewId}/c/${cluster}?node=${encodeURIComponent(focus)}`, { replace: true });
    }).catch(() => {});
    return () => { live = false; };
  }, [board, focus, reviewId, cid, navigate]);
  const info = ov.clusters.find((c) => c.id === cid);
  const name = useCallback((id: string) => ov.clusters.find((c) => c.id === id)?.name ?? id, [ov]);
  const go = (to: string) => navigate(`/r/${reviewId}/c/${to}`);
  const nav = (
    <span className="bd-crumb">
      <Link to={`/r/${reviewId}/overview`}>Overview</Link><span className="sep"> › </span><b>{info?.name ?? cid}</b>
      <button className="bd-ibtn" aria-label="Previous cluster" onClick={() => go(stepCluster(ov, cid, -1))}>‹</button>
      <span className="pos">{cid} of {ov.clusters.length}</span>
      <button className="bd-ibtn" aria-label="Next cluster" onClick={() => go(stepCluster(ov, cid, 1))}>›</button>
      {info && <span className="bd-pill ghost">{info.flows} flows · {info.findings} finding{info.findings === 1 ? "" : "s"}</span>}
    </span>
  );
  const cluster = {
    prefKey, nav, homeName: name,
    onWhole: () => navigate(`/r/${reviewId}/overview`),
    onHome: (c: string, node: string) => navigate(`/r/${reviewId}/c/${c}?node=${encodeURIComponent(node)}`),
    list: ov.clusters.map((c) => ({ id: c.id, name: c.name })),
  };
  if (error)
    return (
      <main className="page">
        <div className="banner warn">{error} {expansion.onReset && <button className="link" onClick={expansion.onReset}>Reset</button>}
          {" "}<Link to={`/r/${reviewId}/overview`}>Back to the overview</Link></div>
      </main>
    );
  if (!board) return <main className="page muted">Loading {info?.name ?? cid}…</main>;
  return (
    <main className="review board">
      <Board key={cid} reviewId={reviewId} board={board} files={files} comments={comments} onComments={onComments} risk={risk}
             focus={focus} openPath={params.get("file")} head={head} cluster={cluster}
             expansion={expansion} />
    </main>
  );
}

/** "+N callers / callees" expansions of a board, kept in the page address (`?x=`) and remembered under `prefKey`. */
export function useExpansion(prefKey: BoardKey) {
  const [params, setParams] = useSearchParams();
  const fromUrl = params.get("x");
  const expand = useMemo(() => (fromUrl !== null ? fromUrl.split(",").filter(Boolean) : loadExpand(prefKey)), [fromUrl, prefKey]);
  const setExpand = useCallback((next: string[]) => {
    save(keys.expand(prefKey), next);
    const p = new URLSearchParams(params);
    p.delete("node");
    if (next.length) p.set("x", next.join(",")); else p.delete("x");
    setParams(p, { replace: true });
  }, [params, prefKey, setParams]);
  const expansion = useMemo(() => ({
    onExpand: (id: string, way: "callers" | "callees") => setExpand(addExpansion(expand, id, way)),
    onReset: expand.length ? () => setExpand([]) : null,
  }), [expand, setExpand]);
  return { expand, expansion };
}
