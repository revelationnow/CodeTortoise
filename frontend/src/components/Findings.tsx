import { useEffect, useRef } from "react";
import { api, type Comment, type Finding } from "../api";
import { useMe } from "../App";
import { SeverityBadge } from "./Badges";
import CiteText, { CiteList } from "./CiteText";
import Comments from "./Comments";
import Explain from "./Explain";

interface Props {
  reviewId: number;
  findings: Finding[];
  focus: string | null;
  comments: Comment[];
  onComments: () => void;
  onFindings: () => void;
  onCite: (id: string) => void;
}

export default function Findings({ reviewId, findings, focus, comments, onComments, onFindings, onCite }: Props) {
  const me = useMe();
  const refs = useRef(new Map<string, HTMLElement>());
  useEffect(() => {
    if (focus) refs.current.get(focus)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [focus]);
  if (!findings.length) return <p className="muted">No findings.</p>;
  return (
    <div className="findings">
      {findings.map((f) => (
        <section key={f.id} ref={(el) => { if (el) refs.current.set(f.id, el); }}
                 className={`card finding ${f.state} ${focus === f.id ? "focus" : ""}`}>
          <div className="row">
            <SeverityBadge severity={f.severity} />
            <h3>{f.id}: {f.title}</h3>
            <span className="muted small">{f.kind}</span>
            {f.state !== "open" && <span className="badge">{f.state}</span>}
            {me?.is_owner && (
              <span className="actions">
                {(["open", "ack", "dismissed"] as const).filter((s) => s !== f.state).map((s) => (
                  <button key={s} className="link small" onClick={() => api.setFindingState(reviewId, f.id, s).then(onFindings)}>{s}</button>
                ))}
              </span>
            )}
          </div>
          <p>{f.summary} <CiteList ids={f.nodes} onCite={onCite} /> <Explain kind="finding" target={f.id} has={!!f.explanation} /></p>
          <h4>Evidence (static analysis)</h4>
          <ul className="evidence">
            {f.evidence.map((e, i) => (
              <li key={i} className={`sev-${e.severity}`}>
                {e.text}
                {e.file && <span className="mono small muted"> {e.file.split("/").slice(-2).join("/")}{e.line ? `:${e.line}` : ""}</span>}
              </li>
            ))}
          </ul>
          {f.explanation && (
            <>
              <h4>Explanation (LLM)</h4>
              <p><CiteText text={f.explanation} onCite={onCite} /></p>
            </>
          )}
          {f.verify_steps.length > 0 && (
            <>
              <h4>Verify</h4>
              <ol>{f.verify_steps.map((s, i) => <li key={i}><CiteText text={s} onCite={onCite} /></li>)}</ol>
            </>
          )}
          {f.hypotheses.length > 0 && (
            <>
              <h4>Possible side effects (LLM, grounded)</h4>
              <ul>{f.hypotheses.map((h, i) => (
                <li key={i}><CiteText text={h.text} onCite={onCite} /> <CiteList ids={h.cites} onCite={onCite} /></li>
              ))}</ul>
            </>
          )}
          <Comments reviewId={reviewId} comments={comments} kind="finding" anchor={{ kind: f.kind, title: f.title }} onChange={onComments} compact />
        </section>
      ))}
    </div>
  );
}
