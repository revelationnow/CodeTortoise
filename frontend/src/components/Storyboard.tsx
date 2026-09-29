import { api, type Comment, type Drift, type Finding, type Impact, type Storyboard as SB } from "../api";
import { useMe } from "../App";
import { RiskBadge, SeverityBadge } from "./Badges";
import CiteText, { CiteList } from "./CiteText";
import Comments from "./Comments";

interface Props {
  reviewId: number;
  sb: SB;
  drift: Drift[];
  impact: Impact | null;
  findings: Finding[];
  comments: Comment[];
  onComments: () => void;
  onCite: (id: string) => void;
  onRenamed: () => void;
}

export default function Storyboard({ reviewId, sb, drift, impact, findings, comments, onComments, onCite, onRenamed }: Props) {
  const me = useMe();
  const rename = (level: number, current: string) => {
    const name = prompt("Layer name (applies to all reviews)", current);
    if (name && name.trim()) api.renameLayer(level, name.trim()).then(onRenamed);
  };
  const byId = new Map(findings.map((f) => [f.id, f]));
  const label = (id: string) => impact?.nodes[id]?.label ?? id;
  return (
    <div className="storyboard">
      {drift.length > 0 && (
        <div className="banner warn">
          <strong>Workspace drift:</strong> {drift.length} file(s) in the base workspace are not at the CL base revision;
          surrounding code is analysed at the workspace revision.
          <ul>{drift.map((d) => <li key={d.depot} className="mono small">{d.depot}: expected {d.expected}, have {d.actual}</li>)}</ul>
        </div>
      )}
      <section className="card summary">
        <div className="row">
          <h2>Summary</h2>
          <RiskBadge risk={sb.risk} />
          {!sb.llm_used && <span className="badge degraded" title={sb.llm_error ?? "no LLM configured"}>deterministic</span>}
          {sb.llm_used && !sb.verified && <span className="badge degraded">unverified</span>}
        </div>
        <p><CiteText text={sb.summary} onCite={onCite} /></p>
        {sb.review_order.length > 0 && (
          <div className="small">
            Suggested review order:{" "}
            {sb.review_order.map((id, i) => (
              <span key={id}>{i > 0 && " → "}<button className="cite" onClick={() => onCite(id)}>{label(id)}</button></span>
            ))}
          </div>
        )}
        <Comments reviewId={reviewId} comments={comments} kind="review" anchor={{}} onChange={onComments} compact />
      </section>
      {[...sb.chapters].reverse().map((ch) => (
        <section key={String(ch.level)} className="card chapter">
          <div className="row">
            <h2>{ch.name}</h2>
            {me?.is_owner && ch.level !== null && (
              <button className="link small" onClick={() => rename(ch.level!, ch.name)}>rename</button>
            )}
            {sb.llm_used && !ch.verified && <span className="badge degraded">unverified</span>}
          </div>
          <p><CiteText text={ch.narrative} onCite={onCite} /> <CiteList ids={ch.cites.filter((c) => !ch.narrative.includes(c))} onCite={onCite} /></p>
          {ch.cross_layer_effects.length > 0 && (
            <>
              <h3>Cross-layer effects</h3>
              <ul>{ch.cross_layer_effects.map((c, i) => (
                <li key={i}><CiteText text={c.text} onCite={onCite} /> <CiteList ids={c.cites} onCite={onCite} /></li>
              ))}</ul>
            </>
          )}
          {ch.nodes.length > 0 && (
            <>
              <h3>Changed functions</h3>
              <ul className="chips">
                {ch.nodes.map((n) => (
                  <li key={n}><button className={`chip st-${impact?.nodes[n]?.status}`} onClick={() => onCite(n)}>{label(n)}</button></li>
                ))}
              </ul>
            </>
          )}
          {ch.findings.length > 0 && (
            <>
              <h3>Findings</h3>
              <ul className="findings-mini">
                {ch.findings.map((fid) => byId.get(fid)).filter(Boolean).map((f) => (
                  <li key={f!.id}>
                    <SeverityBadge severity={f!.severity} />{" "}
                    <button className="link" onClick={() => onCite(f!.id)}>{f!.id}: {f!.title}</button>
                  </li>
                ))}
              </ul>
            </>
          )}
          <Comments reviewId={reviewId} comments={comments} kind="chapter" anchor={{ level: ch.level }} onChange={onComments} compact />
        </section>
      ))}
      <p className="muted small">Chapters run from the highest layer (top) to the lowest.</p>
    </div>
  );
}
