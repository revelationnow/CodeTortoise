import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useMe } from "../App";
import { SeverityBadge } from "../components/Badges";
import Markdown from "../components/Markdown";
import { descriptionParts, plainTitle } from "../lib/markdown";
import { tidy } from "../lib/tidy";
import { clRewrites, gapText } from "../reading/story";
import type { Rewrite } from "../reading/types";
import { useWs } from "./context";
import { short } from "./crumbs";
import { Ticks } from "./NameText";

/** A changelist (spec 2026-10-04-review-workspace §3.4): its description, its Swarm review, its files, and the stories
 * and findings drawn from it. */
export default function ClPage({ cl }: { cl: number }) {
  const ws = useWs(), d = ws.data, me = useMe();
  const [msg, setMsg] = useState<string | null>(null);
  const c = d.detail!.cls.find((x) => x.cl === cl)!;
  const { title, body: rest } = descriptionParts(c.description ?? "");
  const files = d.about?.tree.flatMap((t) => t.files).filter((f) => f.cls.includes(cl)) ?? [];
  const paths = new Set(files.map((f) => f.path));
  const stories = d.stories?.stories.filter((s) => s.cls.includes(cl)) ?? [];
  const findings = d.findings.filter((f) => f.files?.some((p) => paths.has(p)));
  const { rewrites, rewrittenBy } = clRewrites(d.reading?.rewrites, cl);      // phase 2 §5.4
  const gaps = (d.reading?.gaps ?? []).filter((g) => g.after_cl === cl || g.before_cl === cl);
  const base = (p: string) => p.slice(p.lastIndexOf("/") + 1);
  const at = (r: Rewrite) => {
    const name = r.function ?? base(r.file), label = `Open ${name}${r.line ? ` at line ${r.line}` : ""}, in all CLs`;
    return <><Link className="mono" to={ws.link(ws.opened({ file: r.file, line: r.line, all: true }))} title={label} aria-label={label}>{name}</Link>
      {" "}({r.lines} line{r.lines === 1 ? "" : "s"})</>;
  };
  const run = (act: () => Promise<unknown>, ok: string) => {           // a new press clears the last answer
    setMsg(null);
    act().then(() => { setMsg(ok); d.loadDetail(); }).catch((e) => setMsg(String(e.message ?? e)));
  };
  return (
    <div className="ws-page"><div className="ws-text ws-finding">
      <header className="ws-story-head">
        <div className="ws-story-title"><h2>CL {c.cl} · {plainTitle(title) || "(no description)"}</h2></div>
        <p className="ws-story-meta"><span className="muted">{c.user}</span><span className="ws-badge">{c.status}</span></p>
        {rest && <Markdown className="ws-desc" text={rest} />}
      </header>
      <section aria-labelledby="ws-swarm" className="ws-swarm">
        <h3 id="ws-swarm">Swarm</h3>
        {msg && <div className="banner">{msg}</div>}
        {c.swarm ? (
          <p><a href={c.swarm.url} target="_blank" rel="noreferrer" title={`Open Swarm review ${c.swarm.id}`}>Review #{c.swarm.id}</a>{" "}
            <span className="ws-badge">{c.swarm.state_label ?? c.swarm.state}</span>
            {Object.keys(c.swarm.votes).length > 0 && <span className="muted small"> · votes {Object.entries(c.swarm.votes)
              .map(([u, v]) => `${u} ${v > 0 ? "+" : ""}${v}`).join(", ")}</span>}</p>
        ) : <p className="muted">No Swarm review.</p>}
        {me?.is_owner && (
          <p className="ws-tools">
            <button onClick={() => run(() => api.swarmRefresh(d.id, cl), "Swarm state refreshed")}>Refresh</button>
            {!c.swarm && c.status === "pending" && <button onClick={() => run(() => api.swarmCreate(d.id, cl), "Swarm review created")}>Create review</button>}
            {c.swarm && <button onClick={() => run(() => api.swarmPost(d.id, cl).catch((e) => {
              if (e.status === 409 && window.confirm("A summary was already posted. Post again?")) return api.swarmPost(d.id, cl, true);
              throw e;
            }), "Summary link posted to Swarm")}>Post summary link</button>}
          </p>
        )}
      </section>
      <section aria-labelledby="ws-clf">
        <h3 id="ws-clf">Files in this CL</h3>
        {files.length ? <ul className="ws-fx">{files.map((f) => (
          <li key={f.path}><Link className="mono" to={ws.link(ws.opened({ file: f.path, line: null }))} title={`Open ${f.name}'s diff in CL ${cl}`}
                                 aria-label={`Open ${f.name}'s diff in CL ${cl}`}>{f.path}</Link>
            <span className="muted small"> {f.action} <span className="cnt"><span className="p">+{f.add}</span> <span className="m">−{f.rem}</span></span></span></li>
        ))}</ul> : <p className="muted">No files of this CL in the review's change summary.</p>}
      </section>
      {(rewrites.length > 0 || rewrittenBy.length > 0 || gaps.length > 0) && (
        <section aria-labelledby="ws-clrw"><h3 id="ws-clrw">Rewrites</h3>
          <ul className="ws-fx">
            {rewrites.map((r, i) => <li key={`r${i}`}>rewrites lines CL {r.of} added: {at(r)}</li>)}
            {rewrittenBy.map((r, i) => <li key={`b${i}`}>lines it added are rewritten by CL {r.by}: {at(r)}</li>)}
            {gaps.map((g, i) => <li key={`g${i}`}>{gapText(g)}</li>)}
          </ul></section>
      )}
      {stories.length > 0 && (
        <section aria-labelledby="ws-cls"><h3 id="ws-cls">Stories drawn from this CL</h3>
          <ul className="ws-findings">{stories.map((s) => (
            <li key={s.id}>{s.risk && <span className={`bd-pill ${s.risk}`}>{s.risk}</span>}{" "}
              <Link to={ws.link(ws.item({ kind: "story", sid: s.id, view: "steps" }))} title={`Go to story ${s.id}: ${short(s.title)}`}
                    aria-label={`Go to story ${s.id}: ${short(s.title)}`}><Ticks text={s.title} /></Link><span className="ws-handle">{s.id}</span></li>
          ))}</ul></section>
      )}
      {findings.length > 0 && (
        <section aria-labelledby="ws-clfi"><h3 id="ws-clfi">Findings in its files</h3>
          <ul className="ws-findings">{findings.map((f) => (
            <li key={f.id}><SeverityBadge severity={f.severity} />{" "}
              <Link to={ws.link(ws.item({ kind: "finding", fid: f.id }))} title={`Go to finding ${f.id}: ${short(tidy(f.title))}`}
                    aria-label={`Go to finding ${f.id}: ${short(tidy(f.title))}`}>{tidy(f.title)}</Link><span className="ws-handle">{f.id}</span></li>
          ))}</ul></section>
      )}
    </div></div>
  );
}
