import { type ReactNode, useCallback, useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, type Board as BoardModel, type Comment, type FileChange, type Finding, type ReviewDetail } from "../api";
import { useMe } from "../App";
import Board from "../board/Board";
import { driftSummary } from "../board/drift";
import ClsPanel from "../components/ClsPanel";
import Findings from "../components/Findings";
import Stages from "../components/Stages";

const TERMINAL = new Set(["done", "degraded", "failed"]);

export default function Review() {
  const id = Number(useParams().id);
  const me = useMe();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [board, setBoard] = useState<BoardModel | null | undefined>(undefined);   // null: no board for this review
  const [findings, setFindings] = useState<Finding[]>([]);
  const [files, setFiles] = useState<FileChange[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [focus, setFocus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = useCallback(() => api.review(id).then(setDetail).catch((e) => setError(String(e.message ?? e))), [id]);
  const loadComments = useCallback(() => api.comments(id).then(setComments), [id]);
  const loadFindings = useCallback(() => api.findings(id).then(setFindings), [id]);
  const loadResults = useCallback(() => Promise.all([
    api.board(id).then(setBoard).catch((e) => { if (e instanceof ApiError && e.status === 404) setBoard(null); else throw e; }),
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

  const onCite = useCallback((cite: string) => {
    if (cite.startsWith("F")) { setFocus(cite); navigate(`/r/${id}/findings`); }
    else navigate(`/r/${id}?node=${encodeURIComponent(cite)}`);
  }, [id, navigate]);

  if (error) return <main className="page error">{error}</main>;
  if (!detail) return <main className="page muted">Loading…</main>;
  const r = detail.review;
  const ready = TERMINAL.has(r.status);
  const notes = detail.stages.filter((s) => s.status === "failed" || s.status === "degraded");

  const head = (extra?: ReactNode) => (
    <div className="bd-head">
      <h1>{r.title}</h1>
      {r.risk && <span className={`bd-pill ${r.risk}`}>{r.risk.toUpperCase()} RISK</span>}
      {!ready && <span className="bd-pill ghost">{r.status}</span>}
      <span className="bd-pill ghost">{r.cls.map((c) => `CL ${c}`).join(" · ")}</span>
      {board && <span className="bd-pill ghost">{board.flows.length} flows · {findings.length} findings</span>}
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
    <Routes>
      <Route index element={board ? (
        <main className="review board">
          <Board reviewId={id} board={board} files={files} comments={comments} onComments={loadComments} risk={r.risk}
                 focus={params.get("node")} head={head} />
        </main>
      ) : page(board === undefined ? <p className="muted">Loading…</p> : (
        <div className="banner warn">
          No review board for this review (see the stage notes above; reviews made before the board existed have none).
          {me?.is_owner ? " Re-run it to build one." : " The owner can re-run it to build one."} Findings and CLs are still available.
          {me?.is_owner && <> <button onClick={() => api.rerun(id).then(loadDetail)}>Re-run</button></>}
        </div>
      ))} />
      <Route path="findings" element={page(
        <Findings reviewId={id} findings={findings} focus={focus} comments={comments}
                  onComments={loadComments} onFindings={loadFindings} onCite={onCite} />)} />
      <Route path="files" element={<Navigate to={`/r/${id}`} replace />} />
      <Route path="cls" element={page(<ClsPanel reviewId={id} cls={detail.cls} onChange={loadDetail} />)} />
    </Routes>
  );
}
