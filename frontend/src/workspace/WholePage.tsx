import { useMemo } from "react";
import { Link } from "react-router-dom";
import { driftSummary } from "../board/drift";
import { bandsOf, linkLines } from "../board/overview";
import { sideEffectFiles } from "../board/sideEffects";
import type { Board } from "../board/types";
import Comments from "../components/Comments";
import { useWs } from "./context";
import { pickFlow } from "./flows";
import GraphView from "./graph/GraphView";
import NameText from "./NameText";

/** A review shown as one board: its graph, on the whole change page or filling the centre (`?view=graph`). */
export function ReviewGraph({ board, embedded }: { board: Board; embedded?: boolean }) {
  const ws = useWs(), open = ws.addr.open;
  const index = pickFlow(board.flows, ws.addr.flow, open && "node" in open ? open.node : null);
  return <GraphView board={board} prefKey={String(ws.data.id)} flowIndex={index}
                    onFlow={(i) => ws.go({ ...ws.addr, flow: i + 1 }, true)} embedded={embedded} storyOf={ws.data.stories?.node_story} />;
}

/** The review's home (spec 2026-10-04-review-workspace §3.1): what the change is for and why it is risky first. */
export default function WholePage() {
  const ws = useWs(), d = ws.data, about = d.about, risk = d.detail!.review.risk;
  const sideEffects = useMemo(() => (d.board ? sideEffectFiles(d.board) : []), [d.board]);
  const drift = driftSummary(about?.drift ?? []);
  const ov = d.overview;
  const layerName = (level: number | null) => (d.board?.layers ?? ov?.layers ?? []).find((l) => l.level === level)?.name;
  return (
    <div className="ws-page"><div className="ws-text ws-whole">
      <section aria-labelledby="ws-intent">
        <h2 id="ws-intent">What this change is trying to do</h2>
        {about ? <p className="ws-lead">{about.intent_source === "llm" && <span className="ai-label">AI</span>}<NameText text={about.intent} /></p>
          : <p className="muted">No summary for this review (reviews made before the board existed have none).</p>}
      </section>
      {about && about.why.length > 0 && (
        <section aria-labelledby="ws-why">
          <h2 id="ws-why">Why it is {risk ?? "flagged"} risk</h2>
          <ul className="ws-why">{about.why.map((w, i) => (
            <li key={`${w.finding}:${i}`}><span className={`ws-sev ${w.severity}`} aria-hidden />
              <Link to={ws.link(ws.item({ kind: "finding", fid: w.finding }))} title={`Go to finding ${w.finding}`}
                    aria-label={`Go to finding ${w.finding}: ${w.text}`}>{w.text}</Link><span className="ws-handle">{w.finding}</span></li>
          ))}</ul>
        </section>
      )}
      {d.stories && <p className="ws-summary"><NameText text={d.stories.summary} /></p>}
      {ov && (
        <section aria-labelledby="ws-map" id="map">
          <h2 id="ws-map">The map</h2>
          <p className="muted">This change is split into {ov.totals.clusters} parts of connected code, riskiest first.
            {ov.merged_over_limit > 0 && ` ${ov.merged_over_limit} small parts were merged to keep the list short.`}</p>
          {bandsOf(ov).map((b) => (
            <section key={b.level} className={`ov-band lv${b.level < 0 ? "x" : b.level % 4}`} aria-label={`Layer ${b.name}`}>
              <h3>{b.name}</h3>
              <div className="ov-blocks">{b.clusters.map((c) => (
                <Link key={c.id} to={ws.link(ws.item({ kind: "cluster", cid: c.id }))} className={`ov-block ${c.risk ?? "none"}`}
                      title={`Open ${c.name}`} aria-label={`Open ${c.name}`}>
                  <div className="nm">{c.name} {c.risk && <span className={`sev ${c.risk}`}>{c.risk.toUpperCase()}</span>}</div>
                  <div className="ct">{c.files.length} files · {c.changed} changed · {c.flows} flows
                    {c.findings > 0 && ` · ${c.findings} finding${c.findings === 1 ? "" : "s"}`}</div>
                  {linkLines(ov, c.id, 3).map((l) => <div key={l} className="ln">{l}</div>)}
                  {c.also.length > 0 && <div className="also">also in {c.also.map((lv) => layerName(lv) ?? `L${lv}`).join(", ")}</div>}
                </Link>
              ))}</div>
            </section>
          ))}
        </section>
      )}
      {d.board && d.board.nodes.length > 0 && (
        <section aria-labelledby="ws-map" id="map">
          <h2 id="ws-map">The map <Link className="ws-open-full" to={ws.link({ ...ws.addr, place: { kind: "whole", view: "graph" } })}
                                        title="Open the full graph" aria-label="Open the full graph">Open full graph ›</Link></h2>
          <div className="ws-mapgraph"><ReviewGraph board={d.board} embedded /></div>
        </section>
      )}
      {sideEffects.length > 0 && (
        <section aria-labelledby="ws-fx">
          <h2 id="ws-fx">Files with side effects</h2>
          <ul className="ws-fx">{sideEffects.flatMap((dir) => dir.files.map((f) => (
            <li key={f.path}>
              <Link to={ws.link(ws.opened({ file: f.path, line: f.fns[0]?.line ?? null }))} className="mono"
                    title={`Open ${f.name}'s diff`} aria-label={`Open ${f.name}'s diff`}>{dir.dir}/{f.name}</Link>
              {f.alsoChanged && <span className="muted small"> also changed</span>}
              <ul>{f.fns.map((fn) => (
                <li key={fn.node} className={fn.landing ? "landing" : fn.severity}>
                  <Link to={ws.link(ws.opened({ file: f.path, line: fn.line }))} title={`Open ${fn.label} at line ${fn.line}`}
                        aria-label={`Open ${fn.label} at line ${fn.line}`}><b>{fn.label}</b></Link> · {fn.text}
                </li>
              ))}</ul>
            </li>
          )))}</ul>
        </section>
      )}
      {(drift.warn.length > 0 || drift.info.length > 0) && (
        <section aria-labelledby="ws-drift">
          <h2 id="ws-drift">Workspace drift</h2>
          {drift.warn.length > 0 && <p className="banner warn">⚠ {drift.warn.length} file(s): workspace older than the change's base,
            or not synced. Context code fetched from the workspace may not match what was analysed. {drift.warn.join("; ")}</p>}
          {drift.info.length > 0 && <p className="muted">ⓘ {drift.info.length} file(s): workspace newer than the change (expected for
            submitted CLs). {drift.info.join("; ")}</p>}
        </section>
      )}
      <section aria-labelledby="ws-talk">
        <h2 id="ws-talk">Discussion</h2>
        <Comments reviewId={d.id} comments={d.comments} kind="review" anchor={{}} onChange={d.loadComments} />
        {[...new Set(d.comments.filter((c) => c.anchor_kind === "chapter" && c.parent_id === null)
          .map((c) => (typeof c.anchor.level === "number" ? c.anchor.level : null)))]
          .map((level) => (
            <div key={String(level)} className="bd-layer-thread">
              <div className="m">Layer {layerName(level) ?? (level === null ? "unlayered" : `L${level}`)}</div>
              <Comments reviewId={d.id} comments={d.comments} kind="chapter" anchor={{ level }} onChange={d.loadComments} compact />
            </div>
          ))}
      </section>
    </div></div>
  );
}
