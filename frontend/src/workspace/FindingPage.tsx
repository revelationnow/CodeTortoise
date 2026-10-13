import { Link } from "react-router-dom";
import { SeverityBadge } from "../components/Badges";
import { tidy } from "../lib/tidy";
import { useWs } from "./context";
import { short } from "./crumbs";
import FindingBody from "./FindingBody";

/** A finding's own page (spec 2026-10-04-review-workspace §3.3): its title and its place among the findings, then what
 * it says (FindingBody, which the side panel shows too). */
export default function FindingPage({ fid }: { fid: string }) {
  const ws = useWs(), d = ws.data;
  const i = d.findings.findIndex((x) => x.id === fid), f = d.findings[i];
  const n = d.findings.length;
  const step = (by: number) => {
    const to = d.findings[((i + by) % n + n) % n];
    const label = `${by < 0 ? "Previous" : "Next"} finding: ${to.id} ${short(tidy(to.title))}`;
    return <Link className="bd-ibtn ws-step-btn" to={ws.link({ ...ws.item({ kind: "finding", fid: to.id }), details: true })} title={label} aria-label={label}>
      {by < 0 ? "‹" : "›"}</Link>;
  };
  return (
    <div className="ws-page"><div className="ws-text ws-finding">
      <FindingBody fid={fid} ids="ws" head={
        <div className="ws-story-title">
          <h2><SeverityBadge severity={f.severity} /> {tidy(f.title)}</h2>
          <span className="ws-pos">{step(-1)}<span>{f.id} of {n}</span>{step(1)}</span>
        </div>} />
    </div></div>
  );
}
