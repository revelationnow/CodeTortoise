import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { Story, StoryDetail } from "../board/types";
import { keys, load, loadWidth, save } from "../board/prefs";
import Resizer from "../board/Resizer";
import HeadlinePill from "../components/HeadlinePill";
import { CHECK_ORDER, KIND_LABEL, letter, placeOf } from "../reading/checks";
import { causeGroups, causeOpen, doneCount, firstOpenAt, hiddenLabel, shown } from "../reading/causes";
import { threadRead } from "../reading/plan";
import { flowLabel } from "../reading/story";
import type { Cause, Check, CheckKind, Reading } from "../reading/types";
import { INDEX_TABS, type Place } from "./address";
import { useWs } from "./context";
import { INDEX_LABEL, short } from "./crumbs";
import NameText, { Ticks } from "./NameText";
import { plainNames } from "./names";
import Strip, { FoldButton } from "./Strip";

const scrollKey = (rid: number) => `ct.ws.${rid}.railScroll`;
const bare = (s: string) => s.replaceAll("`", "");

type Props = { onPick: () => void; hidden?: boolean };

/** The outline (spec 2026-10-16-outline-and-causes §1.2), for a review with a reading: Stories or Checks, its width
 * handle, its fold to a strip on a desktop and its scroll position per review, as the rail had. Folded, it is hidden,
 * not unmounted, so what the reader set in it survives. */
export default function Outline(props: Props) {
  const ws = useWs(), folded = ws.screen === "desktop" && ws.folds.rail;
  return <>
    {folded && <aside className="ws-rail folded" aria-label="Review contents">
      <Strip name="Contents" label="the contents" side="left" onUnfold={() => ws.setFold("rail", false)} /></aside>}
    <OutlineBody {...props} folded={folded} />
  </>;
}

function OutlineBody({ onPick, hidden = false, folded }: Props & { folded: boolean }) {
  const ws = useWs(), d = ws.data, r = d.reading!;
  const [width, setWidth] = useState(() => Math.min(600, Math.max(200, loadWidth(keys.railW, 280))));
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {                                        // the scroll position, per review and view
    const el = box.current, k = `${scrollKey(d.id)}.${ws.outline}`;
    if (!el) return;
    el.scrollTop = load<number>(k, 0);
    const on = () => save(k, el.scrollTop);
    el.addEventListener("scroll", on, { passive: true });
    return () => el.removeEventListener("scroll", on);
  }, [d.id, folded, ws.outline]);
  return (
    <aside className="ws-rail ws-outline" style={{ ["--w" as string]: `${width}px` }} aria-label="Review contents" inert={hidden} hidden={folded}>
      <Resizer size={width} edge="right" min={200} max={() => 600} onSize={setWidth} onDone={(w) => save(keys.railW, w)} />
      {ws.screen === "desktop" && <FoldButton label="the contents" side="left" onFold={() => ws.setFold("rail", true)} />}
      <div className="ws-outline-switch bd-seg" role="group" aria-label="Show in the outline">
        {(["stories", "checks"] as const).map((v) => (
          <button key={v} className={`bd-ibtn${ws.outline === v ? " on" : ""}`} aria-pressed={ws.outline === v}
                  onClick={() => ws.setOutline(v)}>{v === "stories" ? "Stories" : "Checks"}</button>
        ))}
      </div>
      <div className="ws-rail-scroll" ref={box}>
        {ws.outline === "stories" ? <StoriesView r={r} onPick={onPick} /> : <ChecksView r={r} onPick={onPick} />}
      </div>
    </aside>
  );
}

/** Stories (§1.2): the overview, each thread with its stories in reading order, the current story's flows, the tests,
 * and the Index folded at the bottom. */
function StoriesView({ r, onPick }: { r: Reading; onPick: () => void }) {
  const ws = useWs(), d = ws.data, ss = d.stories;
  const byId = new Map((ss?.stories ?? []).map((st) => [st.id, st]));
  const list = shown(r.causes ?? [], ws.hidden);
  const open = (pick: (c: Cause) => boolean) => list.filter((c) => pick(c) && causeOpen(c, r.marks)).length;
  const read = d.ticks ? new Set(d.ticks.stories) : null;
  const here = ws.addr.place.kind === "story" ? ws.addr.place.sid : null;
  const tests = (ss?.stories ?? []).filter((st) => st.kind === "tests");
  const story = (st: Story, why?: string) => {
    const n = open((c) => c.story === st.id), reason = st.kind === "unsorted" ? "Needs a person to place it" : why;
    const label = `Go to story ${st.id}: ${short(st.title)}${read?.has(st.id) ? " (read)" : ""}${n ? `, ${n} open` : ""}`;
    const place: Place = { kind: "story", sid: st.id, view: "steps" };
    return (
      <li key={st.id}>
        <Link to={ws.link(ws.item(place))} className="ws-row story" aria-current={here === st.id ? "page" : undefined}
              title={bare(st.title)} aria-label={label} onClick={onPick}
              onMouseEnter={() => ws.setHover(st.id)} onMouseLeave={() => ws.setHover(null)}
              onFocus={() => ws.setHover(st.id)} onBlur={() => ws.setHover(null)}>
          <span className="ws-row-top">
            {read && <span className="ws-read" aria-hidden>{read.has(st.id) ? "✓" : ""}</span>}
            <span className="ws-one"><Ticks text={st.title} /></span>
            {n > 0 && <span className="ck-count" aria-hidden>{n}</span>}
          </span>
          {reason && <span className="ws-row-sub">{reason}</span>}
        </Link>
        {here === st.id && <StoryFlows sid={st.id} onPick={onPick} />}
      </li>
    );
  };
  return <>
    <Link to={ws.base} state={{ page: true }} className="ws-row ws-home" aria-current={ws.addr.place.kind === "whole" ? "page" : undefined}
          title="Go to the overview" aria-label="Go to the overview" onClick={onPick}>
      <span aria-hidden>⌂</span> Overview <HeadlinePill h={r.headline} />
    </Link>
    {r.threads.map((t, i) => {
      const n = open((c) => c.thread === t.id);
      return (
        <div key={t.id} className="ws-group ws-thread">
          <h3><span className="ov-letter">{letter(i, t.id)}</span> <Ticks text={t.name} />
            {n > 0 && <span className="ck-count"><span className="vh">, </span>{n}<span className="vh"> open</span></span>}
            {read && <span className="ws-thread-read"><span className="vh">, </span>{threadRead(t.stories, read)}<span className="vh"> read</span></span>}</h3>
          <ul>{t.stories.map((sid) => (byId.get(sid) ? story(byId.get(sid)!, r.reasons[sid]) : null))}</ul>
        </div>
      );
    })}
    {tests.length > 0 && <div className="ws-group"><h3>Tests</h3><ul>{tests.map((st) => story(st))}</ul></div>}
    {!r.threads.length && !tests.length && <p className="muted small ws-pad">No changed functions.</p>}
    <details className="ws-index">
      <summary>Index</summary>
      <ul>{INDEX_TABS.filter((t) => t !== "checks").map((t) => (
        <li key={t}><Link to={ws.link(ws.item({ kind: "index", tab: t }))} className="ws-row ws-index-row"
                          aria-label={`Open the Index: ${INDEX_LABEL[t]}`} title={`Open the Index: ${INDEX_LABEL[t]}`} onClick={onPick}>
          <span className="ws-row-top">{INDEX_LABEL[t]}</span></Link></li>
      ))}</ul>
    </details>
  </>;
}

/** The current story's flows, numbered, one line each; a line opens the story's Flows tab at that flow's card. */
function StoryFlows({ sid, onPick }: { sid: string; onPick: () => void }) {
  const ws = useWs(), d = ws.data, storyOf = d.story;
  const [held, setHeld] = useState<{ sid: string; detail: StoryDetail } | null>(null);
  useEffect(() => {
    let live = true;
    storyOf(sid).then((x) => { if (live) setHeld({ sid, detail: x }); }).catch(() => { /* the page says why */ });
    return () => { live = false; };
  }, [sid, storyOf]);
  const det = held?.sid === sid ? held.detail : null;
  if (!det) return null;
  const flows = det.board.flows.filter((f) => det.story.flows.includes(f.id));
  if (!flows.length) return null;
  const labels = new Map(det.board.nodes.map((n) => [n.id, n.label]));
  const place: Place = { kind: "story", sid, view: "steps" };
  return (
    <ol className="ws-flows">{flows.map((f, i) => {
      const label = flowLabel(f, (n) => labels.get(n) ?? d.names[n]?.label);
      return (
        <li key={f.id}>
          <Link className="ws-row flow" to={ws.link({ ...ws.item(place), place, sec: undefined, flow: i + 1 })}
                aria-current={ws.addr.flow === i + 1 ? "true" : undefined}
                aria-label={`Go to flow ${i + 1}: ${label}`} title={label} onClick={onPick}>
            <span className="ws-row-top"><span className="muted">{i + 1}</span><span className="ws-one mono">{label}</span></span>
          </Link>
        </li>
      );
    })}</ol>
  );
}

/** Checks (§4.4): what is hidden, then each thread's causes by story, each one line with its done count; the checks
 * found no hazard folded at the bottom. */
function ChecksView({ r, onPick }: { r: Reading; onPick: () => void }) {
  const ws = useWs(), d = ws.data;
  if (!r.causes) return <p className="muted small ws-pad">Re-run the review to group its checks.</p>;
  const all = r.causes, list = shown(all, ws.hidden);
  const titles = new Map((d.stories?.stories ?? []).map((st) => [st.id, st.title]));
  const lit = ws.addr.open && "cause" in ws.addr.open ? ws.addr.open.cause : null;
  const flip = (k: CheckKind) => { const h = new Set(ws.hidden); if (!h.delete(k)) h.add(k); ws.setHidden(h); };
  const row = (c: Cause) => {
    const line = bare(plainNames(c.text, d.names)), done = !causeOpen(c, r.marks);
    return (
      <li key={c.id}>
        <Link className={`ws-row cause${done ? " finished" : ""}`} aria-current={lit === c.id ? "true" : undefined}
              to={ws.link(ws.opened({ cause: c.id, at: firstOpenAt(c, r.marks) }))} title={line}
              aria-label={`Open check: ${line}`} onClick={onPick}>
          <span className="ws-row-top"><span className={`ck-tag ${c.kind}`}>{KIND_LABEL[c.kind]}</span>
            <span className="ws-one"><Ticks text={plainNames(c.text, d.names)} /></span>
            <span className="ws-cdone">{done ? "✓" : `${doneCount(c, r.marks)}/${c.places.length}`}</span></span>
        </Link>
      </li>
    );
  };
  return <>
    <details className="ws-hidden">
      <summary>{hiddenLabel(ws.hidden, all)}</summary>
      <ul>{CHECK_ORDER.map((k) => (
        <li key={k}><label><input type="checkbox" checked={!ws.hidden.has(k)} onChange={() => flip(k)} /> {KIND_LABEL[k]}
          <span className="muted small"> {all.filter((c) => c.kind === k).length}</span></label></li>
      ))}</ul>
    </details>
    {causeGroups(r, list).map((g) => (
      <div key={g.thread ?? ""} className="ws-group ws-thread">
        <h3><Ticks text={g.label} /></h3>
        {g.stories.map((s) => (
          <div key={s.story ?? ""} className="ws-cgroup">
            {s.story && <h4 className="ws-one" title={bare(titles.get(s.story) ?? s.story)}><Ticks text={titles.get(s.story) ?? s.story} /></h4>}
            <ul>{s.causes.map(row)}</ul>
          </div>
        ))}
      </div>
    ))}
    {!list.length && <p className="muted small ws-pad">{all.length ? "Every check is of a hidden kind." : "Nothing to check."}</p>}
    <Cleared checks={r.cleared} />
  </>;
}

/** The findings the strong model judged no hazard, folded under their count with their reasons (names, never ids). */
function Cleared({ checks }: { checks: Check[] }) {
  if (!checks.length) return null;
  return (
    <details className="ck-cleared ws-pad">
      <summary>{checks.length} check{checks.length === 1 ? "" : "s"} found no hazard</summary>
      <ul>{checks.map((k) => (
        <li key={k.key}><NameText text={k.text} />{placeOf(k) && <span className="mono small"> · <Ticks text={placeOf(k)} /></span>}</li>
      ))}</ul>
    </details>
  );
}
