import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useMe } from "../App";
import { driftSummary } from "../board/drift";
import AiPill from "../components/AiPill";
import HeadlinePill from "../components/HeadlinePill";
import { useSources } from "../board/useSources";
import Stages from "../components/Stages";
import { AiProvider, useAi } from "../lib/ai";
import { threadLabel } from "../reading/checks";
import { progress, progressText } from "../reading/plan";
import { type Address, at, href, type Open, type Place, readAddress, type Tab } from "./address";
import { useWs, type Ws, WsContext } from "./context";
import Crumbs, { PhoneBar } from "./Crumbs";
import Detail from "./Detail";
import { type Crumb, crumbs } from "./crumbs";
import { useScreen } from "./media";
import { loadMemory, recall, remember, saveMemory } from "./memory";
import ClPage from "./ClPage";
import ClusterPage from "./ClusterPage";
import FindingPage from "./FindingPage";
import IndexPage from "./IndexPage";
import Rail from "./Rail";
import StoryPage from "./StoryPage";
import { indexFor, legacy } from "./legacy";
import { useReview } from "./useReview";
import WholePage, { ReviewGraph } from "./WholePage";
import "./workspace.css";

/** Where the workspace lives (spec 2026-10-04-review-workspace §6). */
export const base = (id: number) => `/r/${id}`;

/** The review workspace (spec 2026-10-04-review-workspace §2): header, rail, centre and the detail panel on demand. */
export default function Workspace() {
  const params = useParams();
  const id = Number(params.id);
  const [q] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const data = useReview(id);
  const screen = useScreen();
  const sources = useSources(id, data.files);
  const [drawer, setDrawer] = useState(false);
  const root = base(id);
  const addr = useMemo(() => readAddress(`/${params["*"] ?? ""}`, q), [params, q]);
  const [memory, setMemory] = useState(() => loadMemory(id));
  useEffect(() => setMemory((m) => remember(m, addr)), [addr]);
  useEffect(() => saveMemory(id, memory), [id, memory]);

  const link = useCallback((a: Address) => href(root, a), [root]);
  const go = useCallback((a: Address, replace = false) => navigate(href(root, a), { replace }), [navigate, root]);
  const item = useCallback((p: Place) => recall(memory, p), [memory]);
  const opened = useCallback((open: Open, tab: Tab = "diff") => ({ ...addr, open, tab }), [addr]);
  const [hover, setHover] = useState<string | null>(null);
  const ws: Ws = useMemo(() => ({ base: root, data, addr, screen, sources, link, go, item, opened, hover, setHover }),
                         [root, data, addr, screen, sources, link, go, item, opened, hover]);

  const d = data.detail;
  const r = data.reading;
  const threadOf = useMemo(() => r ? (sid: string) => threadLabel(r.threads, sid) : undefined, [r]);
  const trail = useMemo(() => crumbs(addr.place, {
    base: root, title: d?.review.title ?? `Review ${id}`, stories: data.stories?.stories ?? [], findings: data.findings,
    cls: d?.cls ?? [], clusters: data.overview?.clusters ?? [], threadOf,
  }), [addr.place, root, d, id, data.stories, data.findings, data.overview, threadOf]);
  const hash = location.hash.slice(1) || null;

  // an address from before the workspace goes to where that thing lives now (§2.3)
  const settled = data.ready && data.stories !== undefined && data.board !== undefined;
  const old = useMemo(() => settled ? legacy(`/${params["*"] ?? ""}`, q, {
    base: root, nodeStory: data.stories?.node_story ?? {}, oneBoard: !!data.board,
  }) : null, [settled, params, q, root, data.stories, data.board]);
  useEffect(() => {
    if (!old) return;
    if ("to" in old) { navigate(old.to, { replace: true }); return; }
    let live = true;                                       // a reader who leaves first stays where they went
    const to = (path: string) => { if (live) navigate(path, { replace: true }); };
    api.locate(id, { node: old.locate }).then(
      (r) => to(r.cluster ? href(root, at({ kind: "cluster", cid: r.cluster }, { open: { node: old.locate } })) : root),
      () => to(root));
    return () => { live = false; };
  }, [old, id, root, navigate]);
  const scrolled = useRef(false);                          // #map or #checks scrolls once, when it is there to scroll to
  useEffect(() => {
    if (hash !== "map" && hash !== "checks") { scrolled.current = false; return; }
    const el = document.getElementById(hash);
    if (el && !scrolled.current) { el.scrollIntoView({ block: "start" }); scrolled.current = true; }
  });
  const page = (location.state as { page?: boolean } | null)?.page || hash === "map" || hash === "checks";
  // with a reading, an old section's anchor (#map, #findings…) opens its Index tab (review reading §11)
  const anchored = r && hash && addr.place.kind === "whole" && !addr.place.view ? indexFor(hash) : null;
  const level = addr.open ? "detail" : addr.place.kind === "whole" && !addr.place.view && !page ? "rail" : "item";

  if (data.error) return <main className="page error">{data.error}</main>;
  if (!d || old) return <main className="page muted">Loading…</main>;
  if (anchored) return <Navigate replace to={href(root, at(anchored))} />;
  return (
    <AiProvider value={data.ai}>
      <WsContext.Provider value={ws}>
        <main className={`ws ${screen} level-${level}${drawer ? " drawer" : ""}`}>
          <Head onMenu={() => setDrawer(!drawer)} drawer={drawer} />
          <div className={`ws-body${addr.open ? " with-detail" : ""}`}>
            {(screen !== "phone" || level === "rail") && <Rail show={hash} onPick={() => setDrawer(false)} hidden={screen === "tablet" && !drawer} />}
            {drawer && <div className="ws-scrim" onClick={() => setDrawer(false)} aria-hidden />}
            {(screen !== "phone" || level === "item") && (
              <section className="ws-centre" aria-label="Centre">
                {screen === "phone" ? <PhoneBar {...phoneBar(trail)} /> : <Crumbs items={trail} />}
                <Centre />
              </section>
            )}
            {addr.open && d && data.ready && (screen !== "phone" || level === "detail") && <Detail key={JSON.stringify(addr.open)} />}
          </div>
        </main>
      </WsContext.Provider>
    </AiProvider>
  );
}

/** "‹ Stories · S1 frame_pop writes…": back to the section, then the item. */
function phoneBar(trail: Crumb[]): { back: Crumb; title: string; handle?: string } {
  if (trail.length === 1) return { back: { label: "Contents", to: trail[0].to ?? "." }, title: "Whole change" };
  const [home, section, me] = trail;
  return me ? { back: section, title: me.label, handle: me.handle } : { back: home, title: section.label };
}

function Head({ onMenu, drawer }: { onMenu: () => void; drawer: boolean }) {
  const ws = useWs(), me = useMe(), ai = useAi(), d = ws.data, r = d.detail!.review;
  const notes = d.detail!.stages.filter((s) => s.status === "failed" || s.status === "degraded");
  const drift = driftSummary(d.about?.drift ?? []).warn;
  return (
    <header className="ws-head">
      <button className="ws-menu" aria-label="Review contents" aria-expanded={drawer} title="Show the review's contents"
              onClick={onMenu}>☰</button>
      <h1><Link to={ws.base} state={{ page: true }} title="Go to the whole change">{r.title}</Link></h1>
      {d.reading ? <HeadlinePill h={d.reading.headline} />
        : r.risk && <span className={`bd-pill ${r.risk}`}>{r.risk.toUpperCase()} RISK</span>}
      {d.reading && d.ticks && <span className="ws-progress">{progressText(progress(d.reading, d.ticks))}</span>}
      {!d.ready && <span className="bd-pill ghost">{r.status}</span>}
      {d.ready && <AiPill />}
      {me?.is_owner && d.ready && <button className="link rerun" onClick={() => api.rerun(d.id).then(d.loadDetail)}>Re-run</button>}
      {me?.is_owner && d.ready && ai?.view?.strong && (
        <button className="link" title="Ask the strong model for new stories instead of reusing the ones it formed for this change"
                onClick={() => api.rerun(d.id, true).then(d.loadDetail)}>Re-run stories (fresh)</button>
      )}
      {drift.length > 0 && <span className="bd-pill high" title={drift.join("\n")}>⚠ workspace drift ({drift.length})</span>}
      {notes.length > 0 && (
        <details className="bd-notes">
          <summary>{notes.length} stage note(s)</summary>
          {notes.map((s) => <div key={s.name} className={`banner ${s.status === "failed" ? "error" : "warn"}`}><strong>{s.name}</strong>: {s.message}</div>)}
        </details>
      )}
    </header>
  );
}

/** What the address names, or what is missing (spec §7). */
function Centre() {
  const ws = useWs(), d = ws.data, p = ws.addr.place;
  if (!d.ready) return <div className="ws-page"><Stages stages={d.detail!.stages} /><p className="muted">Analysis in progress…</p></div>;
  const r = d.reading;
  const exists = p.kind === "whole" || (p.kind === "index" && !!r) || (p.kind === "story" && !!d.stories?.stories.some((s) => s.id === p.sid))
    || (p.kind === "finding" && d.findings.some((f) => f.id === p.fid)) || (p.kind === "cl" && !!d.detail?.cls.some((c) => c.cl === p.cl))
    || (p.kind === "cluster" && !!d.overview?.clusters.some((c) => c.id === p.cid));
  if (!exists) return <Missing what={p} />;
  if (p.kind === "whole" && p.view === "graph")
    return d.board ? <div className="ws-page graph"><ReviewGraph board={d.board} /></div> : <Missing what={p} />;
  if (p.kind === "whole") return <WholePage />;
  if (p.kind === "story") return <StoryPage key={p.sid} sid={p.sid} view={p.view} />;
  if (p.kind === "finding") {
    // with a reading, an old finding address opens its story with its row lit (§11); its own page is Details
    const k = r && !ws.addr.details ? r.checks.find((c) => c.finding === p.fid) : null;
    const sid = k ? k.story ?? d.stories?.finding_story[p.fid] ?? null : null;
    if (k) return <Navigate replace to={ws.link(at(sid ? { kind: "story", sid, view: "steps" } : { kind: "whole" }, { check: p.fid }))} />;
    return <FindingPage key={p.fid} fid={p.fid} />;
  }
  if (p.kind === "cl") return <ClPage key={p.cl} cl={p.cl} />;
  if (p.kind === "cluster") return r ? <IndexPage key={p.cid} tab="map" cid={p.cid} /> : <ClusterPage key={p.cid} cid={p.cid} />;
  if (p.kind === "index") return <IndexPage key={p.tab} tab={p.tab} />;
  return <Missing what={p} />;
}

export function Missing({ what }: { what: Place }) {
  const ws = useWs();
  const name = what.kind === "story" ? `Story ${what.sid}` : what.kind === "finding" ? `Finding ${what.fid}`
    : what.kind === "cl" ? `CL ${what.cl}` : what.kind === "cluster" ? `Part ${what.cid}` : "This page";
  return (
    <div className="ws-page">
      <div className="banner warn">{name} isn't in this review. <Link to={ws.link(at({ kind: "whole" }))} state={{ page: true }}>Whole change</Link></div>
    </div>
  );
}
