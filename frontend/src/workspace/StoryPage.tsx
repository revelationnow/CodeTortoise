import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api";
import type { StoryDetail } from "../board/types";
import Comments from "../components/Comments";
import Explain from "../components/Explain";
import { countLine, stepStory } from "../stories/stories";
import { type Address, at as addressAt } from "./address";
import { useWs } from "./context";
import { short } from "./crumbs";
import { pickFlow } from "./flows";
import FlowStrip from "./FlowStrip";
import GraphView from "./graph/GraphView";
import NameText, { Ticks } from "./NameText";
import { MechanicalStory, TestsStory } from "./StoryBodies";
import StorySteps from "./StorySteps";

/** A story (spec 2026-10-04-review-workspace §3.2): header with the Steps | Graph switch beside the title and ‹ S1 of 4 ›
 * in a fixed-width group; its steps or its graph, with the flow strip. */
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
  const hasGraph = (st.kind === "behaviour" || st.kind === "other") && (!detail || !!detail.graph);
  const shown = hasGraph ? view : "steps";
  const flows = detail ? detail.board.flows.filter((f) => st.flows.includes(f.id)) : [];
  const open = ws.addr.open && "node" in ws.addr.open ? ws.addr.open.node : null;
  const index = pickFlow(flows, ws.addr.flow, open);
  const onFlow = (i: number) => ws.go({ ...ws.addr, flow: i + 1 }, true);
  const step = (by: number) => {
    const to = stepStory(ss, sid, by), other = ss.stories.find((s) => s.id === to);
    const label = `${by < 0 ? "Previous" : "Next"} story: ${to}${other ? ` ${short(other.title)}` : ""}`;
    return <Link className="bd-ibtn ws-step-btn" to={ws.link(ws.item({ kind: "story", sid: to, view: "steps" }))} title={label} aria-label={label}>
      {by < 0 ? "‹" : "›"}</Link>;
  };

  const map: Address | null = st.board ? { ...addressAt({ kind: "cluster", cid: st.board }), story: st.id }   // the story lit on its map
    : d.board ? { ...addressAt({ kind: "whole", view: "graph" }), story: st.id } : null;
  const header = (
    <header className="ws-story-head">
      <div className="ws-story-title">
        <h2>{st.risk && <span className={`bd-pill ${st.risk}`}>{st.risk}</span>}
          {st.text_source === "llm" && <span className="ai-label">AI</span>}<Ticks text={st.title} /></h2>
        {hasGraph && (
          <span className="ws-switch" role="tablist" aria-label="View">
            {(["steps", "graph"] as const).map((v) => (
              <Link key={v} role="tab" aria-selected={shown === v} className={shown === v ? "on" : ""} replace
                    to={ws.link({ ...ws.addr, place: { kind: "story", sid, view: v } })}>{v === "steps" ? "Steps" : "Graph"}</Link>
            ))}
          </span>
        )}
        <span className="ws-pos">{step(-1)}<span>{st.id} of {ss.stories.length}</span>{step(1)}</span>
      </div>
      <p><NameText text={st.summary} /> {st.kind !== "mechanical" && <Explain kind="story" target={st.id} has={st.text_source === "llm"} ask={{ kind: "story", anchor: { id: st.id }, onAsked: d.loadComments }} />}</p>
      <p className="ws-story-meta"><span className="muted">{countLine(st)}</span>
        {st.cls.map((c) => (
          <Link key={c} className="ws-chip" to={ws.link(ws.item({ kind: "cl", cl: c }))} title={`Open CL ${c}`} aria-label={`Open CL ${c}`}>CL {c}</Link>
        ))}
        {map && <Link className="ws-chip ws-onmap" to={ws.link(map)} title={`Show ${st.id} on the map`} aria-label={`Show ${st.id} on the map`}>
          ◎ On the map</Link>}</p>
    </header>
  );
  if (error) return <div className="ws-page"><div className="ws-text">{header}<div className="banner warn">{error}</div></div></div>;
  if (shown === "graph" && !detail)
    return <div className="ws-page graph"><div className="ws-story-bar">{header}</div><p className="muted ws-page">Loading {st.id}…</p></div>;
  if (!detail) return <div className="ws-page"><div className="ws-text">{header}<p className="muted">Loading {st.id}…</p></div></div>;
  if (shown === "graph" && detail.graph)
    return (
      <div className="ws-page graph">
        <div className="ws-story-bar">{header}</div>
        <GraphView key={sid} board={detail.graph} prefKey={`${d.id}.${sid}`} flowIndex={index} onFlow={onFlow} quiet flows={flows}
                   stepsHref={ws.link({ ...ws.addr, place: { kind: "story", sid, view: "steps" } })}
                   onMore={() => ws.go({ ...ws.addr, place: { kind: "story", sid, view: "steps" } }, true)} />
      </div>
    );
  return (
    <div className="ws-page"><div className="ws-text">
      {header}
      {st.kind === "mechanical" ? <MechanicalStory detail={detail} /> : st.kind === "tests" ? <TestsStory detail={detail} /> : <>
        {flows.length > 0 && <FlowStrip board={detail.board} flows={flows} index={index} onFlow={onFlow} steps={false}
                                        hideWhat={!!flows[index] && st.summary.startsWith(flows[index].what)} />}
        <StorySteps detail={detail} flow={flows[index]} />
      </>}
      {at < 0 && <p className="muted">This story isn't in the list.</p>}
      <section aria-labelledby="ws-talk" className="ws-talk">
        <h3 id="ws-talk">Questions and comments</h3>
        <Comments reviewId={d.id} comments={d.comments} kind="story" anchor={{ id: st.id }} onChange={d.loadComments} compact />
      </section>
    </div></div>
  );
}
