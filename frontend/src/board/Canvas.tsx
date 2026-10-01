import { useEffect, useRef, useState } from "react";
import { BAND, type Lens, type Projected, type Viewport } from "./lens";
import { flowSets } from "./layout";
import type { Action, BoardState } from "./reducer";
import type { Board } from "./types";

interface Props {
  board: Board;
  lens: Lens;
  pos: Map<string, Projected>;
  vp: Viewport;
  rows: Map<number, number>;
  state: BoardState;
  dispatch: (a: Action) => void;
  panBy: (dx: number, dy: number) => void;
  onOpenFile: (id: string) => void;
  onInteract: () => void;
}

const KIND = { modified: "Δ modified", added: "Δ added", removed: "Δ removed", signature: "Δ signature" } as const;

/** Layer bands, edges and nodes, all drawn through the lens; pans on drag, moves a node sideways when dragged by it. */
export default function Canvas({ board, lens, pos, vp, rows, state, dispatch, panBy, onOpenFile, onInteract }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const down = useRef<{ x: number; y: number; px: number; py: number; id: number; node: string | null; go: boolean; dragging: boolean } | null>(null);
  const [grab, setGrab] = useState<string | null>(null);   // node being dragged
  const [panning, setPanning] = useState(false);
  const { W } = vp;

  useEffect(() => {                                          // wheel / trackpad pans (non-passive so the page doesn't scroll)
    const el = root.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      panBy(-(e.deltaX + (e.shiftKey ? e.deltaY : 0)), e.shiftKey ? 0 : -e.deltaY);
      onInteract();
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [panBy, onInteract]);

  const graph = state.mode === "graph";
  const flow = board.flows[state.flow];
  const { onPath, pairs } = flowSets(flow, graph);
  const landings = new Set(graph ? board.flows.map((f) => f.lands) : flow ? [flow.lands] : []);
  const front = state.z[state.z.length - 1];
  const byId = new Map(board.nodes.map((n) => [n.id, n]));
  const badge = new Map<string, string>();
  for (const a of board.impacts) if (a.landing && !badge.has(a.node)) badge.set(a.node, a.text);

  // bands: sampled every 16 px so they follow the vertical squeeze
  const xs: number[] = [];
  for (let x = 0; x <= W + 16; x += 16) xs.push(Math.min(x, W));
  const line = (wy: number, rev = false) => (rev ? [...xs].reverse() : xs)
    .map((x, i) => `${i ? "L" : "M"}${x} ${lens.bandY(x, wy).toFixed(1)}`).join(" ");
  const levels = [...rows.entries()].sort((a, b) => a[1] - b[1]);
  const names = new Map(board.layers.map((l) => [l.level, l.name]));

  return (
    <div ref={root} className={`bd-canvas${panning ? " drag" : ""}`}
      onPointerDown={(e) => {
        const t = e.target as HTMLElement, n = t.closest<HTMLElement>(".bd-node");
        down.current = { x: e.clientX, y: e.clientY, px: state.view.panX, py: state.view.panY, id: e.pointerId,
                         node: n?.dataset.id ?? null, go: !!t.closest(".bd-go"), dragging: false };
        e.preventDefault();                                  // no text selection starting on the board
      }}
      onPointerMove={(e) => {
        const d = down.current;
        if (!d) return;
        if (!d.dragging) {
          if (Math.hypot(e.clientX - d.x, e.clientY - d.y) <= 6) return;
          d.dragging = true;
          root.current?.setPointerCapture(d.id);             // only once dragging: early capture swallows clicks
          document.body.classList.add("bd-dragging");
          window.getSelection()?.removeAllRanges();
          if (d.node) setGrab(d.node); else setPanning(true);
          onInteract();
        }
        if (d.node) {
          const r = root.current!.getBoundingClientRect();
          dispatch({ t: "node.move", id: d.node, x: Math.round(lens.unprojectX(e.clientX - r.left)) });
        } else dispatch({ t: "pan", panX: d.px + (e.clientX - d.x), panY: d.py + (e.clientY - d.y) });
      }}
      onPointerUp={() => {
        const d = down.current;
        down.current = null;
        document.body.classList.remove("bd-dragging");
        setGrab(null);
        setPanning(false);
        if (!d || d.dragging || !d.node) return;
        const n = byId.get(d.node);
        if (!n?.path || !n.range) return;
        onInteract();
        if (d.go) onOpenFile(d.node); else dispatch({ t: "card.open", id: d.node });
      }}
      onPointerCancel={() => {
        down.current = null;
        document.body.classList.remove("bd-dragging");
        setGrab(null);
        setPanning(false);
      }}>
      <svg className="bd-bands">
        {levels.map(([lv, i]) => (
          <g key={lv}>
            <path className={`fill${i % 2 ? " alt" : ""}`} d={`${line(i * BAND)} ${line((i + 1) * BAND, true).replace(/^M/, "L")} Z`} />
            <path className="rule" d={line(i * BAND)} />
          </g>
        ))}
        <path className="rule" d={line(levels.length * BAND)} />
      </svg>
      {levels.map(([lv, i]) => {
        const y = lens.bandY(12, i * BAND) + 6, k = Math.max(0.7, (lens.bandY(12, 1) - lens.bandY(12, 0)));
        return <div key={lv} className="bd-blabel" style={{ top: y, transform: `scale(${k})` }}>
          {lv >= 0 ? `L${lv} · ${names.get(lv) ?? ""}` : "other"}
        </div>;
      })}
      <svg className="bd-edges">
        {board.edges.map((e, i) => {
          const p1 = pos.get(e.src), p2 = pos.get(e.dst);
          if (!p1 || !p2) return null;
          const data = e.kind === "writes" || e.kind === "reads";
          const fx = e.kind === "reads" && landings.has(e.src) && (graph || onPath.has(e.dst));
          const inFlow = pairs.has(`${e.src}>${e.dst}`) || pairs.has(`${e.dst}>${e.src}`);
          const my = (p1.y + p2.y) / 2;
          return <path key={i} d={`M${p1.x} ${p1.y} C ${p1.x} ${my}, ${p2.x} ${my}, ${p2.x} ${p2.y}`}
            className={`bd-edge${fx ? " fx" : data ? " data" : ""}${inFlow ? " flow" : ""}${!inFlow && !data && !graph ? " dim" : ""}`} />;
        })}
      </svg>
      {board.nodes.map((n) => {
        const p = pos.get(n.id);
        if (!p) return null;
        const card = state.cards[n.id], on = onPath.has(n.id);
        const cls = ["bd-node", n.change ? "chg" : "", n.kind === "field" ? "field" : "", on ? "onflow" : "",
          !graph && !on && !n.change && !card ? "dim" : "", state.moved[n.id] !== undefined ? "moved" : "",
          card ? "has-card" : "", n.id === front ? "front" : "", grab === n.id ? "grab" : ""].filter(Boolean).join(" ");
        const fx = badge.get(n.id);
        return (
          <div key={n.id} data-id={n.id} className={cls} title={n.label}
               style={{ left: p.x, top: p.y, transform: `translate(-50%, -50%) scale(${p.s})`, zIndex: Math.round(p.s * 20) }}>
            {n.change && <span className="kind">{KIND[n.change.kind]}</span>}
            <span className="lbl">{n.label}</span>
            {n.change && <span className="stat"><b className="p">+{n.change.add}</b><b className="m">−{n.change.rem}</b></span>}
            {!n.change && n.warn > 0 && <span className="warn-dot">{n.warn}</span>}
            {n.path && n.range && <button className="bd-go" title="Open full file" aria-label={`Open ${n.label} in the file viewer`}>⤢</button>}
            {fx && landings.has(n.id) && <div className="fxbadge">⚠ {fx}</div>}
          </div>
        );
      })}
    </div>
  );
}
