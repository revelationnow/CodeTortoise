import { Link } from "react-router-dom";
import type { Placement, StoryDetail } from "../board/types";
import { reasonText, relatedLabel } from "../stories/stories";
import { useWs } from "./context";
import { short } from "./crumbs";
import NameText from "./NameText";

/** What to check and the open questions of a story the strong model formed (spec 2026-10-05-two-tier-stories §10). */
export function StoryChecks({ detail }: { detail: StoryDetail }) {
  const st = detail.story, check = st.check ?? [], questions = st.questions ?? [];
  return <>
    {check.length > 0 && (
      <section aria-labelledby="ws-check"><h3 id="ws-check">What to check</h3>
        <ol>{check.map((c, k) => <li key={k}><NameText text={c} /></li>)}</ol></section>
    )}
    {questions.length > 0 && (
      <section aria-labelledby="ws-questions"><h3 id="ws-questions">Open questions</h3>
        <ul>{questions.map((q, k) => <li key={k}><NameText text={q} /></li>)}</ul></section>
    )}
  </>;
}

/** Why a story's pieces belong together — each piece's files, its reason in words and the pieces and CLs it relies on —
 * and its related stories. The Unsorted story lists its pieces with the check each failed. */
export function StoryWhy({ detail }: { detail: StoryDetail }) {
  const ws = useWs(), ss = ws.data.stories!, st = detail.story;
  const placements = st.placements ?? [], related = st.related ?? [];
  const pieces = new Map((detail.pieces ?? []).map((p) => [p.id, p]));
  const unsorted = st.kind === "unsorted";
  const shown = unsorted || st.source === "tier1" || placements.length > 1;
  const evidence = (e: string) => {
    const cl = /^CL(\d+)$/.exec(e);
    if (cl) return <Link key={e} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: Number(cl[1]) }))}
                         title={`Open CL ${cl[1]}`} aria-label={`Open CL ${cl[1]}`}>CL {cl[1]}</Link>;
    if (pieces.has(e)) return <a key={e} className="ws-handle" href={`#piece-${e}`} title={`Go to piece ${e}`}>{e}</a>;
    const other = ss.stories.find((s) => s.pieces?.includes(e));
    return other ? <Link key={e} className="ws-handle" to={ws.link(ws.item({ kind: "story", sid: other.id, view: "steps" }))}
                         title={`Go to story ${other.id}: ${short(other.title)}`}>{e} · {other.id}</Link>
      : <span key={e} className="ws-handle">{e}</span>;
  };
  const row = (pl: Placement) => {
    const p = pieces.get(pl.piece);
    return (
      <li key={pl.piece} id={`piece-${pl.piece}`}>
        <span className="ws-handle">{pl.piece}</span>
        {p?.files.map((f) => (f.startsWith("//")
          ? <Link key={f} className="mono small" to={ws.link(ws.opened({ file: f, line: null }))} title={`Open ${f}`}
                  aria-label={`Open ${f}`}>{f.split("/").slice(-2).join("/")}</Link>
          : <span key={f} className="mono small">{f}</span>))}
        {p && p.names.length > 0 && <span className="muted small">{p.names.join(", ")}</span>}
        <span className={unsorted ? "ws-reason failed" : "ws-reason"}>{reasonText(pl.reason)}</span>
        {pl.evidence.length > 0 && <span className="ws-evid">{pl.evidence.map(evidence)}</span>}
        {pl.quote.map((q, k) => <q key={k} className="small">{q}</q>)}
      </li>
    );
  };
  return <>
    {shown && placements.length > 0 && (
      <section aria-labelledby="ws-why"><h3 id="ws-why">{unsorted ? "Pieces to place" : "Why these belong together"}</h3>
        {unsorted && <p className="muted">The strong model could not place these, or its placement failed a check: they need a
          person to place them.</p>}
        <ul className="ws-pieces">{placements.map(row)}</ul></section>
    )}
    {related.length > 0 && (
      <section aria-labelledby="ws-related"><h3 id="ws-related">Related</h3>
        <p className="ws-related">{related.map((r) => {
          const other = ss.stories.find((s) => s.id === r);
          return <Link key={r} to={ws.link(ws.item({ kind: "story", sid: r, view: "steps" }))}
                       title={other ? `Go to story ${r}: ${short(other.title)}` : `Go to story ${r}`}>see {relatedLabel(ss, r)}</Link>;
        })}</p></section>
    )}
  </>;
}
