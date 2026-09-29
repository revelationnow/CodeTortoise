import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api, type Comment, type FileChange, type Finding, type Impact, type ReviewDetail, type StoryboardResponse } from "../api";
import { useMe } from "../App";
import { RiskBadge, StatusBadge } from "../components/Badges";
import BlastRadius from "../components/BlastRadius";
import CallFlows from "../components/CallFlows";
import ClsPanel from "../components/ClsPanel";
import Files from "../components/Files";
import Findings from "../components/Findings";
import Stages from "../components/Stages";
import Storyboard from "../components/Storyboard";

const TERMINAL = new Set(["done", "degraded", "failed"]);

export default function Review() {
  const id = Number(useParams().id);
  const me = useMe();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [sb, setSb] = useState<StoryboardResponse | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [files, setFiles] = useState<FileChange[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [focus, setFocus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = useCallback(() => api.review(id).then(setDetail).catch((e) => setError(String(e.message ?? e))), [id]);
  const loadComments = useCallback(() => api.comments(id).then(setComments), [id]);
  const loadFindings = useCallback(() => api.findings(id).then(setFindings), [id]);
  const loadResults = useCallback(() => Promise.all([
    api.storyboard(id).then(setSb), api.impact(id).then(setImpact), loadFindings(), api.files(id).then(setFiles), loadComments(),
  ]), [id, loadFindings, loadComments]);

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

  const layerName = useCallback((level: number | null) => {
    const layer = sb?.storyboard?.chapters.find((c) => c.level === level);
    return layer?.name ?? (level === null ? "unlayered" : `L${level}`);
  }, [sb]);

  const onCite = useCallback((cite: string) => {
    setFocus(cite);
    navigate(cite.startsWith("F") ? `/r/${id}/findings` : `/r/${id}/flows`);
  }, [id, navigate]);

  if (error) return <main className="page error">{error}</main>;
  if (!detail) return <main className="page muted">Loading…</main>;
  const r = detail.review;
  const ready = TERMINAL.has(r.status);
  return (
    <main className="page wide">
      <div className="review-head">
        <h1>{r.title}</h1>
        <StatusBadge status={r.status} />
        <RiskBadge risk={r.risk} />
        <span className="mono muted">CLs {r.cls.join(", ")}</span>
        {me?.is_owner && ready && <button className="link" onClick={() => api.rerun(id).then(loadDetail)}>Re-run</button>}
      </div>
      <Stages stages={detail.stages} />
      {detail.stages.filter((s) => s.status === "failed" || s.status === "degraded").map((s) => (
        <div key={s.name} className={`banner ${s.status === "failed" ? "error" : "warn"}`}><strong>{s.name}</strong>: {s.message}</div>
      ))}
      <nav className="tabs">
        {[["storyboard", "Storyboard"], ["flows", "Call flows"], ["blast", "Blast radius"],
          ["findings", `Findings (${findings.length})`], ["files", `Files (${files.length})`], ["cls", "CLs & Swarm"]].map(([p, label]) => (
          <NavLink key={p} to={`/r/${id}/${p}`} className={({ isActive }) => (isActive ? "on" : "")}>{label}</NavLink>
        ))}
      </nav>
      {!ready ? <p className="muted">Analysis in progress…</p> : (
        <Routes>
          <Route index element={<Navigate to="storyboard" replace />} />
          <Route path="storyboard" element={sb?.storyboard ? (
            <Storyboard reviewId={id} sb={sb.storyboard} drift={sb.drift} impact={impact} findings={findings}
                        comments={comments} onComments={loadComments} onCite={onCite}
                        onRenamed={() => api.storyboard(id).then(setSb)} />
          ) : <p className="muted">No storyboard (see stage messages above).</p>} />
          <Route path="flows" element={impact ? (
            <CallFlows reviewId={id} impact={impact} findings={findings} comments={comments} onComments={loadComments}
                       focus={focus && focus.startsWith("N") ? focus : null} onCite={onCite} layerName={layerName} />
          ) : <p className="muted">No impact model.</p>} />
          <Route path="blast" element={impact ? <BlastRadius impact={impact} onCite={onCite} layerName={layerName} /> : <p className="muted">No impact model.</p>} />
          <Route path="findings" element={
            <Findings reviewId={id} findings={findings} focus={focus && focus.startsWith("F") ? focus : null} comments={comments}
                      onComments={loadComments} onFindings={loadFindings} onCite={onCite} />} />
          <Route path="files" element={<Files reviewId={id} files={files} comments={comments} onComments={loadComments} />} />
          <Route path="cls" element={<ClsPanel reviewId={id} cls={detail.cls} onChange={loadDetail} />} />
        </Routes>
      )}
    </main>
  );
}
