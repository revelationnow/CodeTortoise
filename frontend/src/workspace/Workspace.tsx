import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { keys, load, save } from "../board/prefs";
import Resizer from "../board/Resizer";
import AiPill, { Usage } from "../components/AiPill";
import HeadlinePill from "../components/HeadlinePill";
import { useSources } from "../board/useSources";
import Stages from "../components/Stages";
import { AiProvider, useAi } from "../lib/ai";
import { threadLabel } from "../reading/checks";
import { causeOfCheck, loadHidden, loadOutline, nextOpen, openCount, type OutlineView, progressLine, saveHidden, saveOutline, shown } from "../reading/causes";
import { progress, progressText } from "../reading/plan";
import type { CheckKind } from "../reading/types";
import { type Address, at, href, type Item, type Open, type Place, readAddress, type Tab } from "./address";
import { type Folds, useWs, type Ws, WsContext } from "./context";
import Crumbs, { PhoneBar } from "./Crumbs";
import Detail from "./Detail";
import { type Crumb, crumbs } from "./crumbs";
import { useScreen } from "./media";
import { loadMemory, recall, remember, saveMemory } from "./memory";
import ClPage from "./ClPage";
import ClusterPage from "./ClusterPage";
import FindingPage from "./FindingPage";
import IndexPage from "./IndexPage";
import Outline, { useStoryThread } from "./Outline";
import Rail from "./Rail";
import ReviewMenu from "./ReviewMenu";
import StoryPage from "./StoryPage";
import { addTab, closeTab as closeOf } from "./tabs";
import { HEAD_MIN, headMax, loadHeadH } from "./layout";
import { indexFor, legacy } from "./legacy";
import { bare, plainNames } from "./names";
import { type ReviewData, useReview } from "./useReview";
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
  const [tabs, setTabs] = useState<Item[]>([]);
  useEffect(() => { if (addr.open) setTabs((t) => addTab(t, addr.open!)); }, [addr.open]);
  const closeTab = useCallback((o: Item) => {
    const { tabs: rest, next } = closeOf(tabs, o, addr.open);
    setTabs(rest);
    if (next !== undefined) go({ ...addr, open: next, tab: "diff" }, true);   // closing is not a step to go Back over
  }, [tabs, addr, go]);
  const [folds, setFolds] = useState<Folds>(() => ({ rail: load<unknown>(keys.railFolded, false) === true }));
  const [focus, setFocus] = useState(false);
  const setFold = useCallback((which: keyof Folds, folded: boolean) => {
    setFocus(false);                                       // unfolding by hand ends Focus
    setFolds((f) => ({ ...f, [which]: folded }));
    save(keys.railFolded, folded);
  }, []);
  const toggleFocus = useCallback(() => setFocus((x) => !x), []);
  useEffect(() => { if (!addr.open) setFocus(false); }, [addr.open]);   // closing the panel restores the columns
  const [outline, setOutlineState] = useState<OutlineView>(loadOutline);
  const setOutline = useCallback((v: OutlineView) => { setOutlineState(v); saveOutline(v); }, []);
  const [hidden, setHiddenState] = useState<ReadonlySet<CheckKind>>(loadHidden);
  const setHidden = useCallback((h: ReadonlySet<CheckKind>) => { setHiddenState(h); saveHidden(h); }, []);
  const shown = useMemo(() => (focus ? { rail: true } : folds), [focus, folds]);   // Focus folds the outline only
  const [clsOpen, setClsOpen] = useState<ReadonlySet<number>>(() => new Set());
  const ws: Ws = useMemo(() => ({ base: root, data, addr, screen, sources, link, go, item, opened, hover, setHover,
                                  tabs, closeTab, folds: shown, setFold, focus, toggleFocus,
                                  outline, setOutline, hidden, setHidden, clsOpen, setClsOpen }),
                         [root, data, addr, screen, sources, link, go, item, opened, hover, tabs, closeTab, shown, setFold, focus,
                          toggleFocus, outline, setOutline, hidden, setHidden, clsOpen]);

  const d = data.detail;
  const r = data.reading;
  useStoryThread(id, r, addr.place.kind === "story" ? addr.place.sid : null);   // here, not in the outline: a phone shows no outline beside a story
  const threadOf = useMemo(() => r ? (sid: string) => threadLabel(r.threads, sid) : undefined, [r]);
  const waiting = r === undefined || !loadedFor(addr.place, data);   // the trail waits, as the centre does
  const trail = useMemo(() => waiting && addr.place.kind !== "whole"
    ? [{ label: d?.review.title ?? `Review ${id}`, to: root }, { label: "Loading…", to: null }]
    : crumbs(addr.place, {
      base: root, title: d?.review.title ?? `Review ${id}`, stories: data.stories?.stories ?? [], findings: data.findings,
      cls: d?.cls ?? [], clusters: data.overview?.clusters ?? [], threadOf,
    }), [waiting, addr.place, root, d, id, data.stories, data.findings, data.overview, threadOf]);
  const hash = location.hash.slice(1) || null;

  // an address from before the workspace goes to where that thing lives now (§2.3)
  const settled = data.ready && data.stories !== undefined && data.board !== undefined;
  const old = useMemo(() => settled ? legacy(`/${params["*"] ?? ""}`, q, {
    base: root, nodeStory: data.stories?.node_story ?? {}, oneBoard: !!data.board,
  }) : null, [settled, params, q, root, data.stories, data.board]);
  useEffect(() => {
    if (!old) return;
    if ("to" in old) { if (old.outline) setOutline(old.outline); navigate(old.to, { replace: true }); return; }
    let live = true;                                       // a reader who leaves first stays where they went
    const to = (path: string) => { if (live) navigate(path, { replace: true }); };
    api.locate(id, { node: old.locate }).then(
      (r) => to(r.cluster ? href(root, at({ kind: "cluster", cid: r.cluster }, { open: { node: old.locate } })) : root),
      () => to(root));
    return () => { live = false; };
  }, [old, id, root, navigate, setOutline]);
  // an old `?check=` (a check key, or a finding id from an old finding address) opens the stepper there (§5.2)
  useEffect(() => {
    if (!addr.check || !r?.causes) return;
    const hit = causeOfCheck(r.causes, addr.check);
    go({ ...addr, check: null, ...(hit ? { open: { cause: hit.cause.id, at: hit.at } } : {}) }, true);
  }, [addr, r, go]);
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

  if (data.error) return <main className="page error"><div role="alert">{data.error}</div></main>;
  if (!d || old) return <main className="page muted">Loading…</main>;
  if (anchored) return <Navigate replace to={href(root, at(anchored))} />;
  return (
    <AiProvider value={data.ai}>
      <WsContext.Provider value={ws}>
        <main className={`ws ${screen} level-${level}${drawer ? " drawer" : ""}`}>
          <Head onMenu={() => setDrawer(!drawer)} drawer={drawer} />
          <div className={`ws-body${addr.open ? " with-detail" : ""}`}>
            {(screen !== "phone" || level === "rail") && (r === null      // the old rail only for a review run before the reading
              ? <Rail show={hash} onPick={() => setDrawer(false)} hidden={screen === "tablet" && !drawer} />
              : <Outline onPick={() => setDrawer(false)} hidden={screen === "tablet" && !drawer} />)}
            {drawer && <div className="ws-scrim" onClick={() => setDrawer(false)} aria-hidden />}
            {(screen !== "phone" || level === "item") && (
              <section className="ws-centre" aria-label="Centre">
                {screen === "phone" ? <PhoneBar {...phoneBar(trail)} /> : <Crumbs items={trail} />}
                <Centre />
              </section>
            )}
            {addr.open && d && data.ready && r !== undefined && (screen !== "phone" || level === "detail") && <Detail key={"cause" in addr.open ? `c:${addr.open.cause}` : JSON.stringify(addr.open)} />}
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
  const ws = useWs(), ai = useAi(), d = ws.data, r = d.detail!.review;
  const box = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(loadHeadH);          // null: as tall as its content
  const under = useCallback(() => (box.current?.getBoundingClientRect().bottom ?? 50) + 6, []);
  const [usageTop, setUsageTop] = useState(56);
  useLayoutEffect(() => {                                   // the usage panel sits under the header, whoever opened it
    if (!ai?.usageOpen) return;
    const place = () => setUsageTop(under());
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [ai?.usageOpen, under]);
  const rd = d.reading, causes = rd?.causes;
  const p = rd && d.ticks ? progress(rd, d.ticks) : null;
  const line = !rd || !p ? "" : causes
    ? progressLine(p.stories, p.storyCount, openCount(causes, ws.hidden, rd.marks), shown(causes, ws.hidden).length)
    : progressText(p);
  const next = rd && causes ? nextOpen(causes, ws.hidden, rd.marks, {
    cause: ws.addr.open && "cause" in ws.addr.open ? ws.addr.open.cause : null,
    story: ws.addr.place.kind === "story" ? ws.addr.place.sid : null, order: rd.order }) : null;
  const nextLine = next ? bare(plainNames(causes!.find((c) => c.id === next.cause)!.text, d.names)) : "";
  return (
    <div className="ws-headbox" ref={box} style={height === null ? undefined : { height }}>
      <header className="ws-head">
        <button className="ws-menu" aria-label="Review contents" aria-expanded={drawer} title="Show the review's contents"
                onClick={onMenu}>☰</button>
        <h1><Link to={ws.base} state={{ page: true }} title="Go to the whole change">{r.title}</Link></h1>
        {d.reading ? <HeadlinePill h={d.reading.headline} />
          : d.reading === null && r.risk && <span className={`bd-pill ${r.risk}`}>{r.risk.toUpperCase()} RISK</span>}
        {rd && d.ticks && <span className="ws-progress">{line}</span>}
        {next && <Link className="ws-next" to={ws.link(ws.opened({ cause: next.cause, at: next.at }))} aria-label="Next open check"
                       title={`Next open check: ${nextLine}`}>Next open check ›</Link>}
        {!d.ready && <span className="bd-pill ghost">{r.status}</span>}
        {d.ready && <AiPill />}
        <ReviewMenu under={under} />
      </header>
      {ai?.usageOpen && ai.view?.llm && <Usage top={usageTop} onClose={() => ai.setUsageOpen(false)} />}
      {ws.screen === "desktop" && (
        <Resizer size={() => box.current?.offsetHeight ?? HEAD_MIN} edge="bottom" min={HEAD_MIN} max={() => headMax(window.innerHeight)}
                 onSize={setHeight} onDone={(h) => save(keys.headH, h)} onReset={() => { setHeight(null); save(keys.headH, null); }} />
      )}
    </div>
  );
}

/** What the address names, or what is missing (spec §7). */
function Centre() {
  const ws = useWs(), d = ws.data, p = ws.addr.place;
  if (!d.ready) return <div className="ws-page"><Stages stages={d.detail!.stages} /><p className="muted">Analysis in progress…</p></div>;
  const r = d.reading;
  // the reading decides the layout, and the place's own data whether it is there
  if (r === undefined || !loadedFor(p, d)) return <div className="ws-page"><p className="muted">Loading…</p></div>;
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

/** Whether what tells `p`'s page exists is in (spec §7): until then the page is on its way, not missing. A finding's
 * old address also needs the stories, for the story it opens. */
function loadedFor(p: Place, d: ReviewData): boolean {
  if (p.kind === "story") return d.stories !== undefined;
  if (p.kind === "finding") return d.findingsLoaded && d.stories !== undefined;
  if (p.kind === "cluster") return d.overview !== undefined;
  return !(p.kind === "whole" && p.view === "graph") || d.board !== undefined;
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
