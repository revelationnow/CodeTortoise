import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api";
import type { StoryDetail } from "../board/types";
import Comments from "../components/Comments";
import Explain from "../components/Explain";
import { isOpen } from "../reading/checks";
import { nextUnread } from "../reading/plan";
import { clCounts, stepIn, threadCrumb } from "../reading/story";
import { countLine, reviewTargets, stepStory } from "../stories/stories";
import { type Address, at as addressAt } from "./address";
import { useWs } from "./context";
import { short } from "./crumbs";
import { pickFlow } from "./flows";
import FlowStrip from "./FlowStrip";
import GraphView from "./graph/GraphView";
import NameText, { Ticks } from "./NameText";
import { MechanicalStory, TestsStory } from "./StoryBodies";
import { StoryChecks, StoryWhy } from "./StoryPlan";
import StorySteps from "./StorySteps";
import StoryTiles from "./StoryTiles";

/** Mark as read beside ‹ › (spec 2026-10-07-review-reading-phase2 §6.2): ticks the story for this reader and goes to
 * the next unread story in reading order, or to the overview once every story is read; a read story offers Mark unread. */
function MarkRead({ sid, order }: { sid: string; order: string[] }) {
  const ws = useWs(), d = ws.data, navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const read = d.ticks!.stories.includes(sid);
  const act = (on: boolean) => {
    setBusy(true);
    setError(null);
    d.tick("story", sid, on).then(() => {
      if (!on) return;
      const next = nextUnread(order, new Set([...d.ticks!.stories, sid]), sid);
      if (next) ws.go(ws.item({ kind: "story", sid: next, view: "steps" }));
      else navigate(ws.link(addressAt({ kind: "whole" })), { state: { page: true } });
    }).catch((e) => setError(String(e.message ?? e))).finally(() => setBusy(false));
  };
  return (
    <span className="st-read">
      {read ? <>✓ Read · <button className="link" onClick={() => act(false)} disabled={busy}>Mark unread</button></>
        : <button onClick={() => act(true)} disabled={busy}>Mark as read</button>}
      {error && <span className="banner warn">{error}</span>}
    </span>
  );
}

/** A story (spec 2026-10-04-review-workspace §3.2): header with the Steps | Graph switch beside the title and ‹ › in a
 * fixed-width group; its tiles (spec 2026-10-07-review-reading §6) or its graph with the flow strip. A review run before
 * the reading keeps ‹ S1 of 4 › and the steps with the flow strip. */
export default function StoryPage({ sid, view }: { sid: string; view: "steps" | "graph" }) {
  const ws = useWs(), d = ws.data, ss = d.stories!;
  // held with its story: another story starts loading, while a refreshed one (AI text) replaces it in place
  const [held, setHeld] = useState<{ sid: string; detail: StoryDetail } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const story = d.story;
  useEffect(() => {
    let live = true;
    story(sid).then((x) => { if (live) { setHeld({ sid, detail: x }); setError(null); } })
      .catch((e) => { if (live) setError(e instanceof ApiError && e.status === 404 ? e.message : String(e.message ?? e)); });
    return () => { live = false; };
  }, [story, sid]);
  const detail = held?.sid === sid ? held.detail : null;
  const st = detail?.story ?? ss.stories.find((s) => s.id === sid)!;
  const at = ss.stories.findIndex((s) => s.id === sid);
  // known from the list, so the switch is there at once; gone if the story arrives without a graph after all
  const hasGraph = (st.kind === "behaviour" || st.kind === "other" || st.kind === "unsorted") && (!detail || !!detail.graph);
  const targets = reviewTargets(ss).length > 1 ? st.targets ?? [] : [];      // chips only when the review spans targets
  const shown = hasGraph ? view : "steps";
  const flows = detail ? detail.board.flows.filter((f) => st.flows.includes(f.id)) : [];
  const open = ws.addr.open && "node" in ws.addr.open ? ws.addr.open.node : null;
  const index = pickFlow(flows, ws.addr.flow, open);
  const onFlow = (i: number) => ws.go({ ...ws.addr, flow: i + 1 }, true);
  const r = d.reading, crumb = r ? threadCrumb(r, sid) : null, sr = detail?.reading ?? null;
  const step = (by: number) => {
    const to = r ? stepIn(r.order, sid, by) : stepStory(ss, sid, by), other = ss.stories.find((s) => s.id === to);
    const label = `${by < 0 ? "Previous" : "Next"} story: ${to}${other ? ` ${short(other.title)}` : ""}`;
    return <Link className="bd-ibtn ws-step-btn" to={ws.link(ws.item({ kind: "story", sid: to, view: "steps" }))} title={label} aria-label={label}>
      {by < 0 ? "‹" : "›"}</Link>;
  };

  const hazards = sr ? sr.checks.filter((k) => k.kind === "hazard" && isOpen(k, r?.marks ?? {})).length : 0;
  const map: Address | null = st.board ? { ...addressAt({ kind: "cluster", cid: st.board }), story: st.id }   // the story lit on its map
    : d.board ? { ...addressAt({ kind: "whole", view: "graph" }), story: st.id } : null;
  const header = (
    <header className="ws-story-head">
      {crumb && (
        <p className="st-crumb">
          <Link to={ws.link({ ...addressAt({ kind: "whole" }) })} state={{ page: true }} title={`Go to thread ${crumb.letter} on the overview`}
                aria-label={`Go to thread ${crumb.letter} on the overview`}>Thread {crumb.letter}</Link>
          <span className="sep" aria-hidden> › </span><Ticks text={crumb.name} /><span className="muted"> · {crumb.text}</span>
        </p>
      )}
      <div className="ws-story-title">
        <h2>{!r && st.risk && <span className={`bd-pill ${st.risk}`}>{st.risk}</span>}
          {hazards > 0 && <span className="ct-headline hazard">{hazards} hazard{hazards === 1 ? "" : "s"}</span>}
          {st.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={st.title} /></h2>
        {hasGraph && (
          <span className="ws-switch" role="tablist" aria-label="View">
            {(["steps", "graph"] as const).map((v) => (
              <Link key={v} role="tab" aria-selected={shown === v} className={shown === v ? "on" : ""} replace
                    to={ws.link({ ...ws.addr, place: { kind: "story", sid, view: v } })}>{v === "steps" ? "Steps" : "Graph"}</Link>
            ))}
          </span>
        )}
        <span className="ws-pos">{step(-1)}<span>{r ? (crumb?.text ?? st.id) : `${st.id} of ${ss.stories.length}`}</span>{step(1)}</span>
        {r && d.ticks && <MarkRead sid={sid} order={r.order} />}
      </div>
      <p>{!r && <NameText text={st.summary} />} {st.kind !== "mechanical" && <Explain kind="story" target={st.id} has={st.text_source === "llm"} askOnly={st.source === "tier1"} ask={{ kind: "story", anchor: { id: st.id }, onAsked: d.loadComments }} />}</p>
      <p className="ws-story-meta">{!r && <span className="muted">{countLine(st)}</span>}
        {(sr ? clCounts(sr.where) : st.cls.map((cl) => ({ cl, functions: 0 }))).map(({ cl: c, functions: n }) => (
          <Link key={c} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: c }))} title={`Open CL ${c}`} aria-label={`Open CL ${c}`}>
            CL {c}{n > 0 && ` · ${n} function${n === 1 ? "" : "s"}`}</Link>
        ))}
        {targets.map((t) => <span key={t} className="ws-chip target" title={`Build target ${t}`}>⌖ {t}</span>)}
        {map && <Link className="ws-chip ws-onmap" to={ws.link(map)} title={`Show ${st.id} on the map`} aria-label={`Show ${st.id} on the map`}>
          ◎ On the map</Link>}</p>
    </header>
  );
  const frame = r ? "st-page" : "ws-text";                 // the header keeps its place while the story loads
  if (error) return <div className="ws-page"><div className={frame}>{header}<div className="banner warn">{error}</div></div></div>;
  if (shown === "graph" && !detail)
    return <div className="ws-page graph"><div className="ws-story-bar">{header}</div><p className="muted ws-page">Loading {st.id}…</p></div>;
  if (!detail) return <div className="ws-page"><div className={frame}>{header}<p className="muted">Loading {st.id}…</p></div></div>;
  if (shown === "graph" && detail.graph)
    return (
      <div className="ws-page graph">
        <div className="ws-story-bar">{header}</div>
        <GraphView key={sid} board={detail.graph} prefKey={`${d.id}.${sid}`} flowIndex={index} onFlow={onFlow} quiet flows={flows}
                   stepsHref={ws.link({ ...ws.addr, place: { kind: "story", sid, view: "steps" } })}
                   onMore={() => ws.go({ ...ws.addr, place: { kind: "story", sid, view: "steps" } }, true)} />
      </div>
    );
  if (r && sr)
    return <div className="ws-page"><div className="st-page">{header}<StoryTiles detail={detail} sr={sr} /></div></div>;
  return (
    <div className="ws-page"><div className="ws-text">
      {header}
      <StoryChecks detail={detail} />
      {st.kind === "mechanical" ? <MechanicalStory detail={detail} /> : st.kind === "tests" ? <TestsStory detail={detail} /> : <>
        {flows.length > 0 && <FlowStrip board={detail.board} flows={flows} index={index} onFlow={onFlow} steps={false}
                                        hideWhat={!!flows[index] && st.summary.startsWith(flows[index].what)} />}
        <StorySteps detail={detail} flow={flows[index]} />
      </>}
      <StoryWhy detail={detail} />
      {at < 0 && <p className="muted">This story isn't in the list.</p>}
      <section aria-labelledby="ws-talk" className="ws-talk">
        <h3 id="ws-talk">Questions and comments</h3>
        <Comments reviewId={d.id} comments={d.comments} kind="story" anchor={{ id: st.id }} onChange={d.loadComments} compact />
      </section>
    </div></div>
  );
}
