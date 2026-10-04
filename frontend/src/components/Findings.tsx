import { useEffect, useRef, useState } from "react";
import { api, type Comment, type Finding } from "../api";
import type { ClusterInfo } from "../board/types";
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
  /** A split review's clusters: findings are grouped under them (spec 2026-10-03-large-change-boards §5). */
  groups?: ClusterInfo[];
}

export default function Findings({ reviewId, findings, focus, comments, onComments, onFindings, onCite, groups }: Props) {
  const me = useMe();
  const refs = useRef(new Map<string, HTMLElement>());
  const [only, setOnly] = useState<string>("all");
  useEffect(() => {
    if (focus) refs.current.get(focus)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [focus]);
  if (!findings.length) return <p className="muted">No findings.</p>;
  if (groups) {
    const homed = new Set(groups.flatMap((g) => g.finding_ids));
    const sections = [...groups.map((g) => ({ id: g.id, name: g.name, fs: findings.filter((f) => g.finding_ids.includes(f.id)) })),
                      { id: "rest", name: "The whole change", fs: findings.filter((f) => !homed.has(f.id)) }]
      .filter((s) => s.fs.length && (only === "all" || only === s.id));
    return (
      <div className="findings grouped">
        <label className="fg-filter">Show <select value={only} onChange={(e) => setOnly(e.target.value)} aria-label="Findings of">
          <option value="all">every part</option>
          {groups.filter((g) => g.finding_ids.length).map((g) => <option key={g.id} value={g.id}>{g.id} · {g.name}</option>)}
        </select></label>
        {sections.map((s) => (
          <section key={s.id} className="fg" aria-label={`Findings in ${s.name}`}>
            <h2>{s.id !== "rest" && <span className="fg-id">{s.id}</span>} {s.name} <span className="muted small">{s.fs.length}</span></h2>
            <Findings reviewId={reviewId} findings={s.fs} focus={focus} comments={comments} onComments={onComments}
                      onFindings={onFindings} onCite={onCite} />
          </section>
        ))}
      </div>
    );
  }
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
