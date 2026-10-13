import { Link } from "react-router-dom";
import type { Severity } from "../api";
import { SeverityBadge } from "../components/Badges";
import { tidy } from "../lib/tidy";
import type { Address } from "./address";
import { useWs } from "./context";
import { FINDING_STATES, type FindingState, listFindings, SEVERITIES, STATE_LABEL } from "./findings";

/** Index › Findings (spec 2026-10-12-story-account-and-panels §4): every finding, worst first, filtered by severity and
 * status from the address; a row opens the finding in the side panel. */
export default function FindingsIndex() {
  const ws = useWs(), d = ws.data, sev = ws.addr.sev ?? null, status = ws.addr.status ?? null;
  const rows = listFindings(d.findings, sev, status), story = d.stories?.finding_story ?? {};
  const set = (next: Partial<Pick<Address, "sev" | "status">>) => ws.go({ ...ws.addr, ...next }, true);
  return (
    <section aria-label="Findings" className="ix-findings">
      <div className="ix-filters">
        <label>Severity <select value={sev ?? ""} onChange={(e) => set({ sev: (e.target.value || null) as Severity | null })}>
          <option value="">All</option>{SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
        <label>Status <select value={status ?? ""} onChange={(e) => set({ status: (e.target.value || null) as FindingState | null })}>
          <option value="">All</option>{FINDING_STATES.map((s) => <option key={s} value={s}>{STATE_LABEL[s]}</option>)}</select></label>
        <span className="muted small">{rows.length} of {d.findings.length}</span>
      </div>
      {rows.length === 0 ? <p className="muted">No findings match.</p> : (
        <ul className="ix-list ix-findings-list">{rows.map((f) => {
          const ev = f.evidence.find((e) => e.file);
          const place = ev?.file ? `${ev.file.slice(ev.file.lastIndexOf("/") + 1)}${ev.line ? `:${ev.line}` : ""}` : null;
          const title = tidy(f.title), sid = story[f.id] ?? null;
          const on = !!ws.addr.open && "finding" in ws.addr.open && ws.addr.open.finding === f.id;
          return (
            <li key={f.id} className={on ? "on" : undefined}>
              <SeverityBadge severity={f.severity} />
              <Link className="ix-ftitle" to={ws.link(ws.opened({ finding: f.id }))} title={`${f.id}: ${title}`}
                    aria-label={`Open finding ${f.id} in the side panel`}><span className="ws-handle">{f.id}</span> {title}</Link>
              <span className={`ws-badge state-${f.state}`}>{STATE_LABEL[f.state]}</span>
              {sid && <span className="ws-handle">{sid}</span>}
              {place && <span className="mono small muted" title={ev!.file!}>{place}</span>}
              {f.sink && <span className="ws-chip" title="A write to a shared field">shared field</span>}
            </li>
          );
        })}</ul>
      )}
    </section>
  );
}
