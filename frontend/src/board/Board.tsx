import { type ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from "react";
import type { Comment, FileChange } from "../api";
import "./board.css";
import CardLayer from "./CardLayer";
import Canvas from "./Canvas";
import ChangePanel from "./ChangePanel";
import FileViewer from "./FileViewer";
import FlowBar from "./FlowBar";
import { bandsFor, centrePan, preferDepth, worldNodes } from "./layout";
import { sideEffectFiles } from "./sideEffects";
import { makeLens, type Viewport } from "./lens";
import { keys, loadAboutOpen, loadLayout, loadLens, loadMovedAll, loadSize, loadWidth, save } from "./prefs";
import { type Action, initialState, reduce } from "./reducer";
import type { Board as BoardModel } from "./types";
import PhoneBoard from "./phone/PhoneBoard";
import PhoneMap from "./phone/PhoneMap";
import { fitZoom, pinchView, pinchZoom, zoomLens } from "./zoom";
import { useSources } from "./useSources";

interface Props {
  reviewId: number;
  board: BoardModel;
  files: FileChange[];
  comments: Comment[];
  onComments: () => void;
  risk: string | null;
  /** Node to show (e.g. a finding's cite): its card is opened and the canvas centred on it. */
  focus?: string | null;
  /** Renders the review header (extra content to place in it, if any). */
  head: (extra: ReactNode) => ReactNode;
  /** A cluster's board in a split review (spec 2026-10-03-large-change-boards §5): */
  cluster?: {
    /** Saved layout, moves and tabs are per cluster ("12.C3"). */
    prefKey: string;
    /** Breadcrumb and ‹ ›, shown in the header. */
    nav: ReactNode;
    /** Back to the overview ("Whole change" in the change panel). */
    onWhole: () => void;
    /** A visitor's link: open the board of the cluster it belongs to, focused on it. */
    onHome: (cluster: string, id: string) => void;
    homeName: (cluster: string) => string;
    /** Every cluster, for the phone menu. */
    list: { id: string; name: string }[];
  };
  /** A story's graph (spec 2026-10-04-change-stories §3.1): no lens, quiet field lines, notes on nodes. */
  story?: {
    prefKey: string;
    /** Story title, ‹ › and tabs, shown in the header. */
    nav: ReactNode;
    /** "+N more changed functions": the story's list of them. */
    onMore: () => void;
    /** Phone: the Steps tab's content (desktop shows steps on the story page). */
    steps: ReactNode;
    /** Phone menu: every story. */
    list: { id: string; title: string }[];
    /** Bumped to show the phone's Steps tab ("+N more changed functions"). */
    showSteps: number;
  };
  /** A file to open in the viewer on arrival (the overview's file tree). */
  openPath?: string | null;
  /** "+N callers / +N callees"; with `onReset` when the reader has expanded the board. */
  expansion?: { onExpand: (id: string, way: "callers" | "callees") => void; onReset: (() => void) | null };
}

/** Nodes a board draws before the reader expands it (backend `analysis.board_max_nodes`). */
export const BUDGET = 30;

const wideScreen = () => window.innerWidth > 1100;
const PHONE = "(max-width: 640px)";

/** True while the window is phone-sized (spec §13); follows rotation and resizing. */
export function usePhone() {
  const [phone, setPhone] = useState(() => window.matchMedia(PHONE).matches);
  useEffect(() => {
    const mq = window.matchMedia(PHONE), on = () => setPhone(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return phone;
}

/** The review board (spec §2–§4): flow bar, lensed canvas with cards, file viewer and change panel. */
export default function Board({ reviewId, board, files, comments, onComments, risk, focus, head: reviewHead, cluster, expansion,
  openPath, story }: Props) {
  const prefKey = cluster?.prefKey ?? story?.prefKey ?? reviewId;
  const nav = cluster?.nav ?? story?.nav;
  const head = useCallback((extra: ReactNode) => reviewHead(<>{nav}{extra}</>), [reviewHead, nav]);
  const [state, dispatch] = useReducer(reduce, undefined, () => {
    const lensAt = story ? 0 : loadLens();                // a story graph is small enough to show at full size
    const s = { ...initialState(lensAt, loadMovedAll(prefKey), loadLayout(prefKey) ?? (preferDepth(board) ? "depth" : "layers")),
                about: story ? false : loadAboutOpen() ?? wideScreen() };   // change panel: remembered, else open on wide screens
                                                                             // (a story graph opens with the room for itself)
    return board.flows.length ? s : { ...s, mode: "graph" as const };
  });
  const stateRef = useRef(state);
  stateRef.current = state;
  const sources = useSources(reviewId, files);
  const [vp, setVp] = useState<Viewport>({ W: 0, H: 0 });
  const [viewerW, setViewerW] = useState(() => loadWidth(keys.viewerW, 0));
  const [aboutW, setAboutW] = useState(() => loadWidth(keys.aboutW, 360));
  const [flowH, setFlowH] = useState<number | null>(() => loadSize(keys.flowH, 40, 4000));
  const [hint, setHint] = useState(true);
  const [stage, setStage] = useState<HTMLDivElement | null>(null);   // the canvas element; on phones it mounts with the Map tab
  const phone = usePhone();
  const [zoom, setZoom] = useState(1);                // phone Map, and a story's graph fitted to the canvas (spec §13.4)
  const [sheet, setSheet] = useState<string | null>(null);
  const anim = useRef(0);

  useEffect(() => save(keys.moved(prefKey), state.moved), [prefKey, state.moved]);
  const quiet = !!story;
  useEffect(() => { if (!quiet) save(keys.lens, state.view.lens); }, [quiet, state.view.lens]);
  useEffect(() => { const t = window.setTimeout(() => setHint(false), 7000); return () => window.clearTimeout(t); }, []);
  const interact = useCallback(() => setHint(false), []);

  const sideEffects = useMemo(() => sideEffectFiles(board), [board]);
  const bands = useMemo(() => bandsFor(board, state.layout), [board, state.layout]);
  const world = useMemo(() => worldNodes(board, state.layout, state.moved[state.layout]), [board, state.layout, state.moved]);
  const baseLens = useMemo(() => makeLens(state.view, vp, [...world.values()].map((n) => n.x)), [state.view, vp, world]);
  const lens = useMemo(() => (phone || story ? zoomLens(baseLens, zoom, vp) : baseLens), [phone, story, baseLens, zoom, vp]);
  const pos = useMemo(() => new Map([...world.values()].map((n) => [n.id, lens.project(n.x, n.y)])), [world, lens]);

  const vpRef = useRef(vp);
  vpRef.current = vp;
  const worldRef = useRef(world);
  worldRef.current = world;

  const panTo = useCallback((ids: string[]) => {          // eased pan that centres `ids`
    const { W, H } = vpRef.current, target = centrePan(ids, worldRef.current, W, H);
    if (!target || !W) return;
    window.cancelAnimationFrame(anim.current);
    const { panX: sx, panY: sy } = stateRef.current.view, t0 = performance.now();
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 380), e = 1 - Math.pow(1 - k, 3);
      dispatch({ t: "pan", panX: sx + (target.panX - sx) * e, panY: sy + (target.panY - sy) * e });
      if (k < 1) anim.current = window.requestAnimationFrame(step);
    };
    anim.current = window.requestAnimationFrame(step);
  }, []);

  const panBy = useCallback((dx: number, dy: number) => {
    window.cancelAnimationFrame(anim.current);
    const v = stateRef.current.view;
    dispatch({ t: "pan", panX: v.panX + dx, panY: v.panY + dy });
  }, []);

  // canvas size: keep the focused world point centred when panels open, close or resize
  useLayoutEffect(() => {
    const el = stage;
    if (!el) return;
    let first = true;
    const ro = new ResizeObserver(() => {
      const W = el.clientWidth, H = el.clientHeight, prev = vpRef.current;
      if (prev.W && (W !== prev.W || H !== prev.H)) panBy((W - prev.W) / 2, (H - prev.H) / 2);
      vpRef.current = { W, H };
      setVp({ W, H });
      if (first && W) {
        first = false;
        const s = stateRef.current, f = board.flows[s.flow];
        const ids = s.mode === "flows" && f && !story ? f.path : board.nodes.map((n) => n.id);
        const t = centrePan(ids, worldRef.current, W, H);
        if (t) dispatch({ t: "pan", ...t });
        if (story) { setZoom(fitZoom([...worldRef.current.values()], { W, H })); return; }   // a story's graph opens whole
        const firstChanged = (f?.path ?? []).find((id) => board.nodes.find((n) => n.id === id)?.change)
          ?? board.nodes.find((n) => n.change && n.path && n.range)?.id;
        if (firstChanged && window.innerWidth > 640) dispatch({ t: "card.open", id: firstChanged });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [stage, board, panBy, story]);

  const act = useCallback((a: Action) => { setHint(false); dispatch(a); }, []);
  const toggleAbout = () => { save(keys.about, !state.about); act({ t: "about.toggle" }); };
  const nodes = useMemo(() => new Map(board.nodes.map((n) => [n.id, n])), [board]);
  const openFile = useCallback((id: string) => {
    const n = nodes.get(id);
    if (n?.path) act({ t: "viewer.open", path: n.path, line: n.range?.[0] ?? null, wide: wideScreen() });
  }, [nodes, act]);
  const focused = useRef<string | null>(null);       // a cited node is opened once per citation, not on every resize
  useEffect(() => {
    if (!focus || focus === focused.current || !vp.W || !nodes.get(focus)?.path) return;
    focused.current = focus;
    act({ t: "card.open", id: focus });
    panTo([focus]);
  }, [focus, vp.W, nodes, act, panTo]);
  const opened = useRef<string | null>(null);         // the overview's file tree: open that file once
  useEffect(() => {
    if (!openPath || openPath === opened.current) return;
    opened.current = openPath;
    act({ t: "viewer.open", path: openPath, line: null, wide: wideScreen() });
  }, [openPath, act]);
  const [showMap, setShowMap] = useState(0);           // phone: a citation shows the Map with the function's code sheet
  const sheetFor = useRef<string | null>(null);
  useEffect(() => {                                   // the effect above centres it once the Map has its size
    if (!phone || !focus || focus === sheetFor.current || !nodes.get(focus)?.path) return;
    sheetFor.current = focus;
    setSheet(focus);
    setShowMap((k) => k + 1);
  }, [phone, focus, nodes]);
  const selectFlow = useCallback((i: number) => { act({ t: "flow", i }); panTo(board.flows[i].path); }, [act, panTo, board]);
  const setLayout = (layout: "layers" | "depth") => {
    if (layout === state.layout) return;
    save(keys.layout(prefKey), layout);
    act({ t: "layout", layout });
  };
  const relaid = useRef(state.layout);                // re-centre once the other layout's positions exist
  useEffect(() => {
    if (relaid.current === state.layout) return;
    relaid.current = state.layout;
    panTo(state.mode === "graph" ? board.nodes.map((n) => n.id) : board.flows[state.flow]?.path ?? []);
  }, [state.layout, state.mode, state.flow, board, panTo]);
  const setMode = (mode: "flows" | "graph") => {
    act({ t: "mode", mode });
    panTo(mode === "graph" ? board.nodes.map((n) => n.id) : board.flows[state.flow]?.path ?? []);
  };
  const layerOf = useCallback((id: string) => {
    const lv = nodes.get(id)?.layer ?? -1;
    return board.layers.find((l) => l.level === lv)?.name ?? "unlayered";
  }, [nodes, board]);

  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const anchor = useRef({ x: 0, y: 0 });               // world point under the fingers when the pinch started
  const lensRef = useRef(lens);
  lensRef.current = lens;
  const onPinchStart = useCallback((mid: { x: number; y: number }) => {
    anchor.current = { x: lensRef.current.unprojectX(mid.x), y: lensRef.current.unprojectY(mid.x, mid.y) };
  }, []);
  const onPinch = useCallback((d0: number, d1: number, mid: { x: number; y: number }) => {
    const z1 = pinchZoom(zoomRef.current, d0, d1);
    const next = pinchView(stateRef.current.view, z1, anchor.current, mid, vpRef.current, [...worldRef.current.values()].map((n) => n.x));
    zoomRef.current = z1;
    setZoom(z1);
    window.cancelAnimationFrame(anim.current);
    stateRef.current = { ...stateRef.current, view: next };       // several pinch moves can arrive before a render
    dispatch({ t: "pan", panX: next.panX, panY: next.panY });
  }, []);
  const narrow = typeof window !== "undefined" && window.innerWidth <= 640;
  const viewerOpen = state.viewer.files.length > 0;
  const cardCount = Object.keys(state.cards).length;
  const canvas = vp.W > 0 && <>
    <Canvas board={board} lens={lens} pos={pos} vp={vp} bands={bands} state={state} dispatch={act}
            panBy={panBy} onOpenFile={openFile} onInteract={interact} onExpand={expansion?.onExpand}
            onHome={cluster?.onHome} homeName={cluster?.homeName} quiet={quiet} onMore={story?.onMore}
            touch={phone ? { onPinchStart, onPinch, onTap: setSheet } : undefined} />
    {!phone && <CardLayer reviewId={reviewId} board={board} pos={pos} vp={vp} state={state} dispatch={act} sources={sources}
                          comments={comments} onComments={onComments} onOpenFile={openFile} narrow={narrow} />}
  </>;
  if (phone)
    return (
      <PhoneBoard reviewId={reviewId} board={board} state={state} act={act} sources={sources} comments={comments} clusters={cluster?.list}
                  steps={story?.steps} stories={story?.list} showSteps={story?.showSteps}
                  onComments={onComments} risk={risk} sideEffects={sideEffects} head={head} onOpenFile={openFile}
                  showMap={showMap}
                  map={
                    <PhoneMap reviewId={reviewId} board={board} state={state} act={act} setLayout={setLayout} onFlow={selectFlow}
                              sheet={sheet} onCloseSheet={() => setSheet(null)} onOpenFile={openFile} sources={sources}
                              comments={comments} onComments={onComments}>
                      <div className="bd-stage" ref={setStage}>{canvas}</div>
                    </PhoneMap>
                  } />
    );
  return (
    <div className="bd">
      {head(null)}
      <FlowBar board={board} state={state} layerOf={layerOf} onFlow={selectFlow}
               onStep={(id) => act({ t: "card.toggle", id })} onStepOpen={openFile}
               height={flowH} onHeight={setFlowH} onHeightDone={(h) => { setFlowH(h); save(keys.flowH, h); }} />
      <div className={`bd-main${state.about ? " with-about" : ""}`}>
        <ChangePanel open={state.about} onToggle={toggleAbout} reviewId={reviewId} prefKey={prefKey} onWhole={cluster?.onWhole}
                     comments={comments} onComments={onComments}
                     layers={board.layers} about={board.about} sideEffects={sideEffects} risk={risk} openFiles={state.viewer.files} dispatch={act}
                     wide={wideScreen()} width={aboutW} onWidth={setAboutW} onWidthDone={(w) => save(keys.aboutW, w)} />
        <div className="bd-stage" ref={setStage}>
          {canvas}
          <div className="bd-tools">
            <div className="bd-toolbar">
              <span className="bd-seg">
                <button className={`bd-ibtn${state.mode === "flows" ? " on" : ""}`} disabled={!board.flows.length}
                        onClick={() => setMode("flows")}>Flows</button>
                <button className={`bd-ibtn${state.mode === "graph" ? " on" : ""}`} onClick={() => setMode("graph")}>Whole graph</button>
              </span>
              <span className="bd-seg">
                <button className={`bd-ibtn${state.layout === "layers" ? " on" : ""}`} onClick={() => setLayout("layers")}>Layers</button>
                <button className={`bd-ibtn${state.layout === "depth" ? " on" : ""}`} onClick={() => setLayout("depth")}>Call depth</button>
              </span>
              {Object.keys(state.moved[state.layout]).length > 0 &&
                <button className="bd-ibtn float" onClick={() => act({ t: "layout.reset" })}>Reset layout</button>}
              {!quiet && <>
                <span className="lbl">Lens</span>
                <span className="bd-seg">
                  {([0, 2, 4] as const).map((m) => (
                    <button key={m} className={`bd-ibtn${state.view.lens === m ? " on" : ""}`} onClick={() => act({ t: "lens", lens: m })}>
                      {m ? `${m}×` : "Off"}
                    </button>
                  ))}
                </span>
              </>}
              {cardCount >= 2 && <button className="bd-ibtn float" onClick={() => act({ t: "card.closeAll" })}>Close all cards</button>}
              {expansion?.onReset && (
                <button className="bd-ibtn float over" title="Back to the board as built (you added callers or callees)"
                        onClick={expansion.onReset}>{board.nodes.length} nodes · Reset</button>
              )}
            </div>
            <div className="bd-legend">
              <span className="sw chg" />changed<span className="sw flow" />selected flow<span className="sw field" />field<span className="sw fx" />side effect
            </div>
          </div>
          {hint && <div className="bd-hint">Drag in any direction · tap a function for its card · drag a card by its header · ⤢ opens the full file</div>}
        </div>
        {viewerOpen && (
          <FileViewer reviewId={reviewId} viewer={state.viewer} dispatch={act} sources={sources} anns={board.impacts}
                      comments={comments} onComments={onComments}
                      width={viewerW || Math.min(window.innerWidth * 0.58, 980)} onWidth={setViewerW}
                      onWidthDone={(w) => save(keys.viewerW, w)} />
        )}
      </div>
    </div>
  );
}
