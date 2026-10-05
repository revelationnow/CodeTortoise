import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from "react";
import { bandsFor, centrePan, preferDepth, worldNodes } from "../../board/layout";
import { makeLens, type Viewport } from "../../board/lens";
import { keys, loadLayout, loadLens, loadMovedAll, save } from "../../board/prefs";
import type { Board } from "../../board/types";
import { fitZoom, pinchView, pinchZoom, zoomLens } from "../../board/zoom";
import { useWs } from "../context";
import FlowStrip from "../FlowStrip";
import Canvas from "./Canvas";
import { type GraphAction, initialGraph, reduceGraph } from "./reducer";

interface Props {
  board: Board;
  /** Whose saved layout and moves: "12.S1", "12.C3", "12". */
  prefKey: string;
  flowIndex: number;
  onFlow: (i: number) => void;
  /** A story graph (change stories §3.1): opens whole, no lens, quiet field lines; "+N more" calls `onMore`. */
  quiet?: boolean;
  onMore?: () => void;
  /** A cluster's visitors link to their own cluster. */
  onHome?: (cluster: string, id: string) => void;
  homeName?: (cluster: string) => string;
}

/** A graph in the centre (spec 2026-10-04-review-workspace §5: Board.tsx rebuilt as canvas, flow strip and toolbar).
 * A node click opens its code in the detail panel and a second click closes it; "+N callers" opens Neighbours. */
export default function GraphView({ board, prefKey, flowIndex, onFlow, quiet, onMore, onHome, homeName }: Props) {
  const ws = useWs(), phone = ws.screen === "phone";
  const [state, dispatch] = useReducer(reduceGraph, undefined, () => {
    const s = initialGraph(quiet ? 0 : loadLens(), loadMovedAll(prefKey), loadLayout(prefKey) ?? (preferDepth(board) ? "depth" : "layers"));
    return board.flows.length ? s : { ...s, mode: "graph" as const };
  });
  const stateRef = useRef(state);
  stateRef.current = state;
  const [vp, setVp] = useState<Viewport>({ W: 0, H: 0 });
  const [stage, setStage] = useState<HTMLDivElement | null>(null);
  const [zoom, setZoom] = useState(1);
  const anim = useRef(0);
  const open = ws.addr.open;
  const selected = open && "node" in open ? board.nodes.find((n) => n.id === open.node || n.fields?.some((f) => f.id === open.node))?.id ?? null : null;
  const lit = useMemo(() => new Set(open && "file" in open ? board.nodes.filter((n) => n.path === open.file).map((n) => n.id) : []),
                      [open, board]);

  useEffect(() => save(keys.moved(prefKey), state.moved), [prefKey, state.moved]);
  useEffect(() => { if (!quiet) save(keys.lens, state.view.lens); }, [quiet, state.view.lens]);
  const bands = useMemo(() => bandsFor(board, state.layout), [board, state.layout]);
  const world = useMemo(() => worldNodes(board, state.layout, state.moved[state.layout]), [board, state.layout, state.moved]);
  const baseLens = useMemo(() => makeLens(state.view, vp, [...world.values()].map((n) => n.x)), [state.view, vp, world]);
  const lens = useMemo(() => (phone || quiet ? zoomLens(baseLens, zoom, vp) : baseLens), [phone, quiet, baseLens, zoom, vp]);
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

  useLayoutEffect(() => {                                // canvas size: keep the middle where it was as panels open and close
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
        const f = board.flows[flowIndex];
        const ids = stateRef.current.mode === "flows" && f && !quiet ? f.path : board.nodes.map((n) => n.id);
        const t = centrePan(ids, worldRef.current, W, H);
        if (t) dispatch({ t: "pan", ...t });
        if (quiet || phone) setZoom(fitZoom([...worldRef.current.values()], { W, H }));
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [stage, board, panBy, quiet, phone]);                // eslint-disable-line react-hooks/exhaustive-deps

  const shownFlow = useRef(flowIndex);                   // a new flow: pan to it
  useEffect(() => {
    if (shownFlow.current === flowIndex) return;
    shownFlow.current = flowIndex;
    if (board.flows[flowIndex]) { dispatch({ t: "mode", mode: "flows" }); panTo(board.flows[flowIndex].path); }
  }, [flowIndex, board, panTo]);
  const centred = useRef<string | null>(null);           // a node opened from elsewhere (a link, a finding): centre it once
  useEffect(() => {
    if (!selected || selected === centred.current || !vp.W) return;
    centred.current = selected;
    if (pos.get(selected) && (pos.get(selected)!.x < 0 || pos.get(selected)!.x > vp.W || pos.get(selected)!.y < 0 || pos.get(selected)!.y > vp.H))
      panTo([selected]);
  }, [selected, vp, pos, panTo]);
  const relaid = useRef(state.layout);
  useEffect(() => {
    if (relaid.current === state.layout) return;
    relaid.current = state.layout;
    panTo(state.mode === "graph" ? board.nodes.map((n) => n.id) : board.flows[flowIndex]?.path ?? []);
  }, [state.layout, state.mode, flowIndex, board, panTo]);

  const act = useCallback((a: GraphAction) => dispatch(a), []);
  const setLayout = (layout: "layers" | "depth") => { if (layout !== state.layout) { save(keys.layout(prefKey), layout); act({ t: "layout", layout }); } };
  const setMode = (mode: "flows" | "graph") => {
    act({ t: "mode", mode });
    panTo(mode === "graph" ? board.nodes.map((n) => n.id) : board.flows[flowIndex]?.path ?? []);
  };
  const onSelect = (id: string) => ws.go(ws.opened(id === selected ? null : { node: id }));
  const onNeighbours = (id: string) => ws.go(ws.opened({ node: id }, "neighbours"));

  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const anchor = useRef({ x: 0, y: 0 });
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
    stateRef.current = { ...stateRef.current, view: next };
    dispatch({ t: "pan", panX: next.panX, panY: next.panY });
  }, []);

  return (
    <div className="bd ws-graph">
      {board.flows.length > 0 && (
        <FlowStrip board={board} flows={board.flows} index={flowIndex} steps onFlow={(i) => { onFlow(i); }} />
      )}
      <div className="bd-stage" ref={setStage}>
        {vp.W > 0 && (
          <Canvas board={board} lens={lens} pos={pos} vp={vp} bands={bands} state={state} dispatch={act} panBy={panBy}
                  flow={state.mode === "flows" ? board.flows[flowIndex] : undefined} selected={selected} lit={lit}
                  onSelect={onSelect} onNeighbours={onNeighbours} onHome={onHome} homeName={homeName} quiet={quiet} onMore={onMore}
                  touch={phone ? { onPinchStart, onPinch } : undefined} />
        )}
        <div className="bd-tools">
          <div className="bd-toolbar">
            {board.flows.length > 0 && (
              <span className="bd-seg">
                <button className={`bd-ibtn${state.mode === "flows" ? " on" : ""}`} aria-pressed={state.mode === "flows"}
                        onClick={() => setMode("flows")}>Flow</button>
                <button className={`bd-ibtn${state.mode === "graph" ? " on" : ""}`} aria-pressed={state.mode === "graph"}
                        onClick={() => setMode("graph")}>Whole graph</button>
              </span>
            )}
            <span className="bd-seg">
              <button className={`bd-ibtn${state.layout === "layers" ? " on" : ""}`} aria-pressed={state.layout === "layers"}
                      onClick={() => setLayout("layers")}>Layers</button>
              <button className={`bd-ibtn${state.layout === "depth" ? " on" : ""}`} aria-pressed={state.layout === "depth"}
                      onClick={() => setLayout("depth")}>Call depth</button>
            </span>
            {Object.keys(state.moved[state.layout]).length > 0 &&
              <button className="bd-ibtn float" onClick={() => act({ t: "layout.reset" })}>Reset layout</button>}
            {!quiet && <>
              <span className="lbl">Lens</span>
              <span className="bd-seg">{([0, 2, 4] as const).map((m) => (
                <button key={m} className={`bd-ibtn${state.view.lens === m ? " on" : ""}`} aria-pressed={state.view.lens === m}
                        onClick={() => act({ t: "lens", lens: m })}>{m ? `${m}×` : "Off"}</button>
              ))}</span>
            </>}
          </div>
          <div className="bd-legend">
            <span className="sw chg" />changed<span className="sw flow" />selected flow<span className="sw field" />field<span className="sw fx" />side effect
          </div>
        </div>
      </div>
    </div>
  );
}
