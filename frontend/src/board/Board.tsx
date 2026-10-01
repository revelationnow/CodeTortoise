import { type ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from "react";
import type { Comment, FileChange } from "../api";
import "./board.css";
import CardLayer from "./CardLayer";
import Canvas from "./Canvas";
import ChangePanel from "./ChangePanel";
import FileViewer from "./FileViewer";
import FlowBar from "./FlowBar";
import { centrePan, layerRows, worldNodes } from "./layout";
import { makeLens, type Viewport } from "./lens";
import { keys, loadLens, loadMoved, loadWidth, save } from "./prefs";
import { type Action, initialState, reduce } from "./reducer";
import type { Board as BoardModel } from "./types";
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
  /** Renders the review header; receives the "What's this change?" button to place in it. */
  head: (aboutButton: ReactNode) => ReactNode;
}

const wideScreen = () => window.innerWidth > 1100;

/** The review board (spec §2–§4): flow bar, lensed canvas with cards, file viewer and change panel. */
export default function Board({ reviewId, board, files, comments, onComments, risk, focus, head }: Props) {
  const [state, dispatch] = useReducer(reduce, undefined, () => {
    const s = initialState(loadLens(), loadMoved(reviewId));
    return board.flows.length ? s : { ...s, mode: "graph" as const };
  });
  const stateRef = useRef(state);
  stateRef.current = state;
  const sources = useSources(reviewId, files);
  const [vp, setVp] = useState<Viewport>({ W: 0, H: 0 });
  const [viewerW, setViewerW] = useState(() => loadWidth(keys.viewerW, 0));
  const [aboutW, setAboutW] = useState(() => loadWidth(keys.aboutW, 360));
  const [hint, setHint] = useState(true);
  const stage = useRef<HTMLDivElement>(null);
  const anim = useRef(0);

  useEffect(() => save(keys.moved(reviewId), state.moved), [reviewId, state.moved]);
  useEffect(() => save(keys.lens, state.view.lens), [state.view.lens]);
  useEffect(() => { const t = window.setTimeout(() => setHint(false), 7000); return () => window.clearTimeout(t); }, []);
  const interact = useCallback(() => setHint(false), []);

  const rows = useMemo(() => layerRows(board), [board]);
  const world = useMemo(() => worldNodes(board, state.moved), [board, state.moved]);
  const lens = useMemo(() => makeLens(state.view, vp, [...world.values()].map((n) => n.x)), [state.view, vp, world]);
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
    const el = stage.current;
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
        const ids = s.mode === "flows" && f ? f.path : board.nodes.map((n) => n.id);
        const t = centrePan(ids, worldRef.current, W, H);
        if (t) dispatch({ t: "pan", ...t });
        const firstChanged = (f?.path ?? []).find((id) => board.nodes.find((n) => n.id === id)?.change)
          ?? board.nodes.find((n) => n.change && n.path && n.range)?.id;
        if (firstChanged && window.innerWidth > 640) dispatch({ t: "card.open", id: firstChanged });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [board, panBy]);

  const act = useCallback((a: Action) => { setHint(false); dispatch(a); }, []);
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
  const selectFlow = useCallback((i: number) => { act({ t: "flow", i }); panTo(board.flows[i].path); }, [act, panTo, board]);
  const setMode = (mode: "flows" | "graph") => {
    act({ t: "mode", mode });
    panTo(mode === "graph" ? board.nodes.map((n) => n.id) : board.flows[state.flow]?.path ?? []);
  };
  const layerOf = useCallback((id: string) => {
    const lv = nodes.get(id)?.layer ?? -1;
    return board.layers.find((l) => l.level === lv)?.name ?? "unlayered";
  }, [nodes, board]);

  const narrow = typeof window !== "undefined" && window.innerWidth <= 640;
  const viewerOpen = state.viewer.files.length > 0;
  const cardCount = Object.keys(state.cards).length;
  return (
    <div className="bd">
      {head(<button className="bd-about-btn" onClick={() => act({ t: "about.toggle" })}>✦ What's this change?</button>)}
      <FlowBar board={board} state={state} layerOf={layerOf} onFlow={selectFlow}
               onStep={(id) => act({ t: "card.toggle", id })} onStepOpen={openFile} />
      <div className={`bd-main${state.about ? " with-about" : ""}`}>
        <div className="bd-stage" ref={stage}>
          {vp.W > 0 && <>
            <Canvas board={board} lens={lens} pos={pos} vp={vp} rows={rows} state={state} dispatch={act}
                    panBy={panBy} onOpenFile={openFile} onInteract={interact} />
            <CardLayer reviewId={reviewId} board={board} pos={pos} vp={vp} state={state} dispatch={act} sources={sources}
                       comments={comments} onComments={onComments} onOpenFile={openFile} narrow={narrow} />
          </>}
          <div className="bd-tools">
            <div className="bd-toolbar">
              <span className="bd-seg">
                <button className={`bd-ibtn${state.mode === "flows" ? " on" : ""}`} disabled={!board.flows.length}
                        onClick={() => setMode("flows")}>Flows</button>
                <button className={`bd-ibtn${state.mode === "graph" ? " on" : ""}`} onClick={() => setMode("graph")}>Whole graph</button>
              </span>
              {Object.keys(state.moved).length > 0 && <button className="bd-ibtn float" onClick={() => act({ t: "layout.reset" })}>Reset layout</button>}
              <span className="lbl">Lens</span>
              <span className="bd-seg">
                {([0, 2, 4] as const).map((m) => (
                  <button key={m} className={`bd-ibtn${state.view.lens === m ? " on" : ""}`} onClick={() => act({ t: "lens", lens: m })}>
                    {m ? `${m}×` : "Off"}
                  </button>
                ))}
              </span>
              {cardCount >= 2 && <button className="bd-ibtn float" onClick={() => act({ t: "card.closeAll" })}>Close all cards</button>}
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
        {state.about && (
          <ChangePanel reviewId={reviewId} comments={comments} onComments={onComments} layers={board.layers} about={board.about} risk={risk} openFiles={state.viewer.files} dispatch={act} wide={wideScreen()}
                       width={aboutW} onWidth={setAboutW} onWidthDone={(w) => save(keys.aboutW, w)} />
        )}
      </div>
    </div>
  );
}
