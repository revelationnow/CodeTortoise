import { useEffect, useRef, useState } from "react";
import { type Band, flowSets } from "../../board/layout";
import { BAND, type Lens, type Projected, type Viewport } from "../../board/lens";
import type { Board, BoardFlow } from "../../board/types";
import type { GraphAction, GraphState } from "./reducer";

interface Props {
  board: Board;
  lens: Lens;
  pos: Map<string, Projected>;
  vp: Viewport;
  bands: Band[];
  state: GraphState;
  dispatch: (a: GraphAction) => void;
  panBy: (dx: number, dy: number) => void;
  /** The flow to highlight (flows mode). */
  flow: BoardFlow | undefined;
  /** The node open in the detail panel, and the nodes of the file open there. */
  selected: string | null;
  lit: Set<string>;
  /** A node click: open its code, or close it when it is the one open (spec 2026-10-04-review-workspace §3.2). */
  onSelect: (id: string) => void;
  /** "+N callers / +N callees": its Neighbours tab. */
  onNeighbours?: (id: string) => void;
  /** A visitor's link to the board of the cluster it belongs to. */
  onHome?: (cluster: string, id: string) => void;
  /** A cluster id's name, for the visitor link. */
  homeName?: (cluster: string) => string;
  /** A story graph (spec 2026-10-04-change-stories §3.1): field lines and calls off the selected flow show only for
   * the selected node; "+N more changed functions" calls `onMore`. */
  quiet?: boolean;
  onMore?: () => void;
  /** A map on a scrolling page: a plain wheel scrolls the page; the map takes the wheel with Ctrl, Meta or Shift held, or
   * once clicked or focused, until the pointer leaves it. */
  embedded?: boolean;
  /** Phones: two-finger pinch; a node moves only after a long press. */
  touch?: {
    onPinchStart: (mid: { x: number; y: number }) => void;
    onPinch: (d0: number, d1: number, mid: { x: number; y: number }) => void;
  };
}

const LONG_PRESS = 450;

const KIND = { modified: "Δ modified", added: "Δ added", removed: "Δ removed", signature: "Δ signature" } as const;

/** Layer bands, edges and nodes, all drawn through the lens; pans on drag, moves a node when dragged by it. */
export default function Canvas({ board, lens, pos, vp, bands, state, dispatch, panBy, flow, selected, lit, onSelect, onNeighbours,
  touch, onHome, homeName, quiet, onMore, embedded }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const engaged = useRef(false);                             // an embedded map, clicked or focused: it takes the wheel
  const down = useRef<{ x: number; y: number; px: number; py: number; id: number; node: string | null; act: string | null;
                        dragging: boolean; ox: number; oy: number; armed: boolean; timer: number } | null>(null);
  const pts = useRef(new Map<number, { x: number; y: number }>());     // touch: active pointers
  const pinch = useRef<{ d: number } | null>(null);
  const spread = () => {
    const [a, b] = [...pts.current.values()];
    const r = root.current!.getBoundingClientRect();
    return { d: Math.hypot(a.x - b.x, a.y - b.y), mid: { x: (a.x + b.x) / 2 - r.left, y: (a.y + b.y) / 2 - r.top } };
  };
  const end = () => {
    if (down.current) window.clearTimeout(down.current.timer);
    down.current = null;
    document.body.classList.remove("bd-dragging");
    setGrab(null);
    setPanning(false);
  };
  const [grab, setGrab] = useState<string | null>(null);   // node being dragged
  const [panning, setPanning] = useState(false);
  const { W } = vp;

  useEffect(() => {                                          // wheel / trackpad pans (non-passive so the page doesn't scroll)
    const el = root.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (embedded && !engaged.current && !(e.ctrlKey || e.metaKey || e.shiftKey)) return;   // the page scrolls
      e.preventDefault();
      panBy(-(e.deltaX + (e.shiftKey ? e.deltaY : 0)), e.shiftKey ? 0 : -e.deltaY);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [panBy, embedded]);

  const graph = state.mode === "graph";
  const { onPath, pairs } = flowSets(flow, graph);
  const landings = new Set(graph ? board.flows.map((f) => f.lands) : flow ? [flow.lands] : []);
  const front = selected;
  const byId = new Map(board.nodes.map((n) => [n.id, n]));
  const badge = new Map<string, string>();
  for (const a of board.impacts) if (a.landing && !badge.has(a.node)) badge.set(a.node, a.text);

  // bands: sampled every 16 px so they follow the vertical squeeze
  const xs: number[] = [];
  for (let x = 0; x <= W + 16; x += 16) xs.push(Math.min(x, W));
  const line = (wy: number, rev = false) => (rev ? [...xs].reverse() : xs)
    .map((x, i) => `${i ? "L" : "M"}${x} ${lens.bandY(x, wy).toFixed(1)}`).join(" ");

  return (
    <div ref={root} className={`bd-canvas${panning ? " drag" : ""}`}
      onFocus={() => { engaged.current = true; }}
      onBlur={(e) => { if (!root.current?.contains(e.relatedTarget as Node | null)) engaged.current = false; }}
      onPointerLeave={() => { if (!down.current) engaged.current = false; }}
      onPointerDown={(e) => {
        e.preventDefault();                                  // no text selection starting on the board
        engaged.current = true;
        if (touch) {
          pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
          if (pts.current.size === 2) {                      // a second finger: pinch, never a drag or a tap
            end();
            const s = spread();
            pinch.current = { d: s.d };
            touch.onPinchStart(s.mid);
            root.current?.setPointerCapture(e.pointerId);
            return;
          }
          if (pts.current.size > 2) return;
        }
        const t = e.target as HTMLElement, n = t.closest<HTMLElement>(".bd-node"), r = root.current!.getBoundingClientRect();
        const at = n?.dataset.id ? pos.get(n.dataset.id) : undefined;     // keep the grab point under the pointer
        const d = { x: e.clientX, y: e.clientY, px: state.view.panX, py: state.view.panY, id: e.pointerId,
                    node: n?.dataset.id ?? null, act: t.closest<HTMLElement>("[data-act]")?.dataset.act ?? null,
                    dragging: false,
                    ox: at ? at.x - (e.clientX - r.left) : 0, oy: at ? at.y - (e.clientY - r.top) : 0,
                    armed: !touch, timer: 0 };
        if (touch && d.node)                                 // touch: a node moves only after a long press
          d.timer = window.setTimeout(() => { if (down.current === d && !d.dragging) { d.armed = true; setGrab(d.node); } }, LONG_PRESS);
        down.current = d;
      }}
      onPointerMove={(e) => {
        if (touch && pts.current.has(e.pointerId)) pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (touch && pinch.current && pts.current.size === 2) {
          const { d, mid } = spread();
          touch.onPinch(pinch.current.d, d, mid);
          pinch.current.d = d;
          return;
        }
        const d = down.current;
        if (!d || d.id !== e.pointerId) return;
        if (!d.dragging) {
          if (Math.hypot(e.clientX - d.x, e.clientY - d.y) <= 6) return;
          d.dragging = true;
          window.clearTimeout(d.timer);
          if (!d.armed) d.node = null;                       // touch without a long press: pan, don't move the node
          root.current?.setPointerCapture(d.id);             // only once dragging: early capture swallows clicks
          document.body.classList.add("bd-dragging");
          window.getSelection()?.removeAllRanges();
          if (d.node) setGrab(d.node); else setPanning(true);
        }
        if (d.node) {
          const r = root.current!.getBoundingClientRect(), sx = e.clientX - r.left + d.ox, sy = e.clientY - r.top + d.oy;
          dispatch({ t: "node.move", id: d.node, x: Math.round(lens.unprojectX(sx)), y: Math.round(lens.unprojectY(sx, sy)) });
        } else dispatch({ t: "pan", panX: d.px + (e.clientX - d.x), panY: d.py + (e.clientY - d.y) });
      }}
      onPointerUp={(e) => {
        if (touch) {
          pts.current.delete(e.pointerId);
          if (pinch.current) { if (pts.current.size < 2) pinch.current = null; return; }
        }
        const d = down.current;
        if (d && d.id !== e.pointerId) return;
        end();
        if (!d || d.dragging || !d.node) return;
        const n = byId.get(d.node);
        if (n?.kind === "more") { onMore?.(); return; }
        if (d.act) {                                         // a badge or a visitor's home link, not the node
          if (d.act === "home" && n?.home) onHome?.(n.home, d.node);
          else if (d.act === "callers" || d.act === "callees") onNeighbours?.(d.node);
          return;
        }
        const id = d.node;                                   // after the tap's click, or it lands in the panel that opens under it
        if (touch) window.setTimeout(() => onSelect(id), 0); else onSelect(id);
      }}
      onPointerCancel={(e) => {
        pts.current.delete(e.pointerId);
        if (pts.current.size < 2) pinch.current = null;
        end();
      }}>
      <svg className="bd-bands">
        {bands.map(({ key, row: i }) => (
          <g key={key}>
            <path className={`fill${i % 2 ? " alt" : ""}`} d={`${line(i * BAND)} ${line((i + 1) * BAND, true).replace(/^M/, "L")} Z`} />
            <path className="rule" d={line(i * BAND)} />
          </g>
        ))}
        <path className="rule" d={line(bands.length * BAND)} />
      </svg>
      {bands.map(({ key, row: i, label }) => {
        const y = lens.bandY(12, i * BAND) + 6, k = Math.max(0.7, (lens.bandY(12, 1) - lens.bandY(12, 0)));
        return <div key={key} className="bd-blabel" style={{ top: y, transform: `scale(${k})` }}>
          {label}
        </div>;
      })}
      <svg className="bd-edges">
        {board.edges.map((e, i) => {
          const p1 = pos.get(e.src), p2 = pos.get(e.dst);
          if (!p1 || !p2) return null;
          const data = e.kind === "writes" || e.kind === "reads";
          const fx = e.kind === "reads" && landings.has(e.src) && (graph || onPath.has(e.dst));
          const inFlow = pairs.has(`${e.src}>${e.dst}`) || pairs.has(`${e.dst}>${e.src}`);
          if (quiet && !inFlow && e.src !== front && e.dst !== front && (data || !graph)) return null;
          const my = (p1.y + p2.y) / 2;
          return <path key={i} d={`M${p1.x} ${p1.y} C ${p1.x} ${my}, ${p2.x} ${my}, ${p2.x} ${p2.y}`}
            className={`bd-edge${fx ? " fx" : data ? " data" : ""}${inFlow ? " flow" : ""}${!inFlow && !data && !graph ? " dim" : ""}`} />;
        })}
      </svg>
      {board.nodes.map((n) => {
        const p = pos.get(n.id);
        if (!p) return null;
        const sel = n.id === selected, on = onPath.has(n.id);
        const cls = ["bd-node", n.change ? "chg" : "", n.kind === "field" || n.kind === "struct" ? "field" : "", n.kind === "more" ? "more" : "",
          n.note ? "noted" : "", on ? "onflow" : "", n.home ? "visitor" : "",
          !graph && !on && !n.change && !sel && !lit.has(n.id) ? "dim" : "", state.moved[state.layout][n.id] !== undefined ? "moved" : "",
          sel ? "has-card front" : "", lit.has(n.id) ? "lit" : "", grab === n.id ? "grab" : ""].filter(Boolean).join(" ");
        const fx = badge.get(n.id);
        return (
          <div key={n.id} data-id={n.id} className={cls} title={sel ? `Close ${n.label}'s code` : `Open ${n.label}'s code`}
               role="button" aria-label={sel ? `Close ${n.label}'s code` : `Open ${n.label}'s code`} aria-pressed={sel}
               style={{ left: p.x, top: p.y, transform: `translate(-50%, -50%) scale(${p.s})`, zIndex: Math.round(p.s * 20),
                        ["--hit" as string]: `${40 / Math.max(p.s, 0.1)}px` }}>
            {n.change && <span className="kind">{KIND[n.change.kind]}</span>}
            <span className="lbl">{n.label}</span>
            {n.note && <span className="note">{n.note.replace(/`/g, "")}</span>}
            {!!n.fields?.length && <span className="fields">{n.fields.map((f) => <span key={f.id}>.{f.label}</span>)}</span>}
            {n.change && <span className="stat"><b className="p">+{n.change.add}</b><b className="m">−{n.change.rem}</b></span>}
            {!n.change && n.warn > 0 && <span className="warn-dot">{n.warn}</span>}
            {fx && landings.has(n.id) && !n.note && <div className="fxbadge">⚠ {fx}</div>}
            {n.home && onHome && <span className="bd-home" data-act="home" role="button" title={`Go to ${homeName?.(n.home) ?? n.home}`}
                                       aria-label={`Go to ${homeName?.(n.home) ?? n.home}`}>
              · {homeName?.(n.home) ?? n.home} ›</span>}
            {onNeighbours && (!!n.more_callers || !!n.more_callees) && (
              <span className="bd-more-nb">
                {!!n.more_callers && <span data-act="callers" role="button" title={`Show ${n.label}'s callers`}
                                           aria-label={`Show ${n.label}'s callers`}>+{n.more_callers} callers</span>}
                {!!n.more_callees && <span data-act="callees" role="button" title={`Show ${n.label}'s callees`}
                                           aria-label={`Show ${n.label}'s callees`}>+{n.more_callees} callees</span>}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
