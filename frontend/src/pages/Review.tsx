import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, type AiJob, type Board as BoardModel, type Comment, type FileChange, type Finding, type Overview, type ReviewDetail } from "../api";
import { useMe } from "../App";
import Board from "../board/Board";
import ClusterBoard, { useExpansion } from "../board/ClusterBoard";
import OverviewPage from "../board/OverviewPage";
import { driftSummary } from "../board/drift";
import AiPill from "../components/AiPill";
import ClsPanel from "../components/ClsPanel";
import Findings from "../components/Findings";
import Stages from "../components/Stages";
import { AiProvider, useAiState } from "../lib/ai";

const TERMINAL = new Set(["done", "degraded", "failed"]);

export default function Review() {
  const id = Number(useParams().id);
  const me = useMe();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [board, setBoard] = useState<BoardModel | null | undefined>(undefined);   // null: no board for this review
  const [overview, setOverview] = useState<Overview | null | undefined>(undefined);  // a split review's (null: one board)
  const [reload, setReload] = useState(0);              // cluster boards fetch again after an AI explanation
  const [findings, setFindings] = useState<Finding[]>([]);
  const [files, setFiles] = useState<FileChange[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [focus, setFocus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = useCallback(() => api.review(id).then(setDetail).catch((e) => setError(String(e.message ?? e))), [id]);
  const loadComments = useCallback(() => api.comments(id).then(setComments), [id]);
  const loadFindings = useCallback(() => api.findings(id).then(setFindings), [id]);
  const loadResults = useCallback(() => Promise.all([
    api.overview(id).then((ov) => { setOverview(ov); setBoard(null); }).catch((e) => {
      if (!(e instanceof ApiError && e.status === 404)) throw e;
      setOverview(null);
      return api.board(id).then(setBoard).catch((e2) => { if (e2 instanceof ApiError && e2.status === 404) setBoard(null); else throw e2; });
    }),
    loadFindings(), api.files(id).then(setFiles), loadComments(),
  ]).catch((e) => setError(String(e.message ?? e))), [id, loadFindings, loadComments]);

  useEffect(() => { loadDetail(); }, [loadDetail]);

  const status = detail?.review.status;
  useEffect(() => {
    if (!status) return;
    if (TERMINAL.has(status)) { loadResults(); return; }
    const es = new EventSource(`/api/reviews/${id}/events`);
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      setDetail((d) => (d ? { ...d, review: data.review, stages: data.stages } : d));
      if (TERMINAL.has(data.review.status)) { es.close(); loadDetail(); }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [id, status, loadResults, loadDetail]);

  const ready = !!status && TERMINAL.has(status);
  const people = useMemo(() => [...new Set([detail?.review.created_by ?? "", ...comments.map((c) => c.author)])].filter(Boolean),
                         [detail, comments]);
  const onAiDone = useCallback((jobs: AiJob[]) => {   // an explanation finished: show it
    if (jobs.some((j) => j.kind === "flow")) {
      if (overview) setReload((k) => k + 1);
      else api.board(id).then(setBoard).catch(() => {});
    }
    if (jobs.some((j) => j.kind === "finding")) loadFindings();
  }, [id, loadFindings, overview]);
  const ai = useAiState(id, ready, people, comments.some((c) => c.ai_meta?.pending), onAiDone, loadComments);

  const onCite = useCallback((cite: string) => {
    if (cite.startsWith("F")) { setFocus(cite); navigate(`/r/${id}/findings`); }
    else navigate(`/r/${id}?node=${encodeURIComponent(cite)}`);
  }, [id, navigate]);

  if (error) return <main className="page error">{error}</main>;
  if (!detail) return <main className="page muted">Loading…</main>;
  const r = detail.review;
  const notes = detail.stages.filter((s) => s.status === "failed" || s.status === "degraded");

  const head = (extra?: ReactNode) => (
    <div className="bd-head">
      <h1>{r.title}</h1>
      {r.risk && <span className={`bd-pill ${r.risk}`}>{r.risk.toUpperCase()} RISK</span>}
      {!ready && <span className="bd-pill ghost">{r.status}</span>}
      <span className="bd-pill ghost">{r.cls.map((c) => `CL ${c}`).join(" · ")}</span>
      {board && <span className="bd-pill ghost">{board.flows.length} flows · {findings.length} findings</span>}
      {ready && <AiPill />}
      <nav aria-label="Review sections">
        <NavLink end to={`/r/${id}`} className={({ isActive }) => (isActive ? "on" : "")}>Board</NavLink>
        <NavLink to={`/r/${id}/findings`} className={({ isActive }) => (isActive ? "on" : "")}>Findings ({findings.length})</NavLink>
        <NavLink to={`/r/${id}/cls`} className={({ isActive }) => (isActive ? "on" : "")}>CLs &amp; Swarm</NavLink>
      </nav>
      {me?.is_owner && ready && <button className="link rerun" onClick={() => api.rerun(id).then(loadDetail)}>Re-run</button>}
      {board && driftSummary(board.about.drift).warn.length > 0 && (
        <span className="bd-pill high" title={driftSummary(board.about.drift).warn.join("\n")}>
          ⚠ workspace drift ({driftSummary(board.about.drift).warn.length})</span>
      )}
      {notes.length > 0 && (
        <details className="bd-notes">
          <summary>{notes.length} stage note(s)</summary>
          {notes.map((s) => <div key={s.name} className={`banner ${s.status === "failed" ? "error" : "warn"}`}><strong>{s.name}</strong>: {s.message}</div>)}
        </details>
      )}
      {extra}
    </div>
  );
  const page = (body: ReactNode) => (
    <main className="review">{head()}<div className="review-body">{body}</div></main>
  );

  if (!ready)
    return page(<><Stages stages={detail.stages} /><p className="muted">Analysis in progress…</p></>);
  return (
    <AiProvider value={ai}>
    <Routes>
      <Route index element={overview ? (
        params.get("node") ? <Locate reviewId={id} node={params.get("node")!} /> : (
          <main className="review board">
            <OverviewPage reviewId={id} ov={overview} comments={comments} onComments={loadComments} risk={r.risk} head={head}
                          onOpen={(c, file) => navigate(`/r/${id}/c/${c}${file ? `?file=${encodeURIComponent(file)}` : ""}`)} />
          </main>
        )
      ) : board ? (
        <SingleBoard reviewId={id} board={board} files={files} comments={comments} onComments={loadComments} risk={r.risk}
                     focus={params.get("node")} head={head} />
      ) : page(board === undefined || overview === undefined ? <p className="muted">Loading…</p> : (
        <div className="banner warn">
          No review board for this review (see the stage notes above; reviews made before the board existed have none).
          {me?.is_owner ? " Re-run it to build one." : " The owner can re-run it to build one."} Findings and CLs are still available.
          {me?.is_owner && <> <button onClick={() => api.rerun(id).then(loadDetail)}>Re-run</button></>}
        </div>
      ))} />
      <Route path="c/:cid" element={overview ? (
        <ClusterRoute reviewId={id} ov={overview} files={files} comments={comments} onComments={loadComments} risk={r.risk}
                      head={head} reload={reload} />
      ) : page(<p className="muted">{overview === null ? "This review is shown as one board." : "Loading…"}</p>)} />
      <Route path="findings" element={page(
        <Findings reviewId={id} findings={findings} focus={focus} comments={comments} groups={overview?.clusters}
                  onComments={loadComments} onFindings={loadFindings} onCite={onCite} />)} />
      <Route path="files" element={<Navigate to={`/r/${id}`} replace />} />
      <Route path="cls" element={page(<ClsPanel reviewId={id} cls={detail.cls} onChange={loadDetail} />)} />
    </Routes>
    </AiProvider>
  );
}

/** `/r/:id?node=N12` on a split review: open the board of the cluster that shows the node. */
function Locate({ reviewId, node }: { reviewId: number; node: string }) {
  const navigate = useNavigate();
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    api.locate(reviewId, { node }).then(({ cluster }) => {
      if (cluster) navigate(`/r/${reviewId}/c/${cluster}?node=${encodeURIComponent(node)}`, { replace: true });
      else setMissing(true);
    }).catch(() => setMissing(true));
  }, [reviewId, node, navigate]);
  return <main className="page muted">{missing ? `${node} isn't on any board of this review.` : `Finding ${node}…`}</main>;
}

/** A review shown as one board; "+N callers" fetches it again with the expansions (spec §3). */
function SingleBoard({ board, ...p }: Omit<Parameters<typeof Board>[0], "expansion">) {
  const { expand, expansion } = useExpansion(p.reviewId);
  const [grown, setGrown] = useState<BoardModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setError(null);
    if (!expand.length) { setGrown(null); return; }
    api.board(p.reviewId, undefined, expand).then((b) => { if (live) setGrown(b); })
      .catch((e) => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [p.reviewId, expand, board]);
  return (
    <main className="review board">
      {error && <div className="banner warn">{error} <button className="link" onClick={() => expansion.onReset?.()}>Reset</button></div>}
      <Board {...p} board={expand.length && grown ? grown : board} expansion={expansion} />
    </main>
  );
}

function ClusterRoute(p: Omit<Parameters<typeof ClusterBoard>[0], "cid">) {
  const cid = useParams().cid!;
  return <ClusterBoard key={cid} {...p} cid={cid} />;
}
