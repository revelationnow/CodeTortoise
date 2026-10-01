import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Comment } from "../api";
import CodeView from "./CodeView";
import { lineDiff, plainLines, sliceRange } from "./codeRows";
import { placeCards } from "./layout";
import type { Projected, Viewport } from "./lens";
import type { Action, BoardState } from "./reducer";
import type { Board, BoardNode } from "./types";
import { isChange, useEnsureSource, type useSources } from "./useSources";

type Sources = ReturnType<typeof useSources>;
interface Props {
  reviewId: number;
  board: Board;
  pos: Map<string, Projected>;
  vp: Viewport;
  state: BoardState;
  dispatch: (a: Action) => void;
  sources: Sources;
  comments: Comment[];
  onComments: () => void;
  onOpenFile: (id: string) => void;
  narrow: boolean;
}

/** Floating code cards: one per open node, placed next to it through the lens, tethered to it. */
export default function CardLayer(p: Props) {
  const { board, pos, vp, state, narrow } = p;
  const els = useRef(new Map<string, HTMLDivElement>());
  const ro = useRef<ResizeObserver | null>(null);
  const [sizes, setSizes] = useState<Record<string, { w: number; h: number }>>({});
  useEffect(() => () => ro.current?.disconnect(), []);
  const register = useCallback((id: string, el: HTMLDivElement | null) => {
    ro.current ??= new ResizeObserver((entries) => setSizes((prev) => {
      let next = prev;
      for (const e of entries) {
        const t = e.target as HTMLDivElement, key = t.dataset.id!, w = t.offsetWidth, h = t.offsetHeight;
        if (prev[key]?.w !== w || prev[key]?.h !== h) next = { ...next, [key]: { w, h } };
      }
      return next;
    }));
    const old = els.current.get(id);
    if (old && old !== el) ro.current.unobserve(old);
    if (el) { els.current.set(id, el); ro.current.observe(el); } else els.current.delete(id);
  }, []);

  const nodes = useMemo(() => new Map(board.nodes.map((n) => [n.id, n])), [board]);
  const ids = state.z.filter((id) => state.cards[id] && pos.get(id) && nodes.get(id));
  const rects = placeCards(ids.map((id) => {
    const c = state.cards[id];
    return { id, at: pos.get(id)!, w: sizes[id]?.w ?? (c.collapsed ? 140 : 460), h: sizes[id]?.h ?? (c.collapsed ? 34 : 320),
             collapsed: c.collapsed, offset: c.offset };
  }), vp.W, vp.H);
  const front = state.z[state.z.length - 1];

  return (
    <>
      <svg className="bd-tethers">
        {ids.map((id) => {
          const r = rects.get(id)!, at = pos.get(id)!;
          if (narrow && !state.cards[id].collapsed) return null;
          const tx = r.x + (r.x > at.x ? 0 : r.w), ty = Math.max(r.y + 14, Math.min(at.y, r.y + r.h - 14));
          return <path key={id} className={id === front ? "front" : ""} d={`M${at.x} ${at.y} L ${tx} ${ty}`} />;
        })}
      </svg>
      {ids.map((id, i) => (
        <Card key={id} {...p} node={nodes.get(id)!} rect={rects.get(id)!} at={pos.get(id)!} z={50 + i}
              front={id === front} register={register} />
      ))}
    </>
  );
}

interface CardProps extends Props {
  node: BoardNode;
  rect: { x: number; y: number; k: number };
  at: Projected;
  z: number;
  front: boolean;
  register: (id: string, el: HTMLDivElement | null) => void;
}

function Card({ node, rect, at, z, front, register, state, dispatch, narrow, onOpenFile, ...rest }: CardProps) {
  const id = node.id, collapsed = state.cards[id].collapsed;
  const drag = useRef<{ x: number; y: number; left: number; top: number; moved: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);
  const sheet = narrow && !collapsed;
  const changed = !!node.change;
  return (
    <div ref={(el) => register(id, el)} data-id={id}
         className={`bd-card${changed ? "" : " ctx"}${collapsed ? " min" : ""}${front ? " front" : ""}${sheet ? " sheet" : ""}${dragging ? " dragged" : ""}`}
         style={sheet ? { zIndex: z } : { left: rect.x, top: rect.y, transform: `scale(${rect.k})`, zIndex: z }}
         onPointerDown={(e) => { e.stopPropagation(); dispatch({ t: "card.front", id }); }}
         onClick={() => { if (collapsed) dispatch({ t: "card.expand", id }); }}>
      <div className="hd"
           onPointerDown={(e) => {
             if ((e.target as HTMLElement).closest("button") || collapsed || narrow) return;
             drag.current = { x: e.clientX, y: e.clientY, left: rect.x, top: rect.y, moved: false };
             e.currentTarget.setPointerCapture(e.pointerId);
           }}
           onPointerMove={(e) => {
             const d = drag.current;
             if (!d) return;
             const dx = e.clientX - d.x, dy = e.clientY - d.y;
             if (!d.moved && Math.hypot(dx, dy) < 4) return;
             if (!d.moved) setDragging(true);
             d.moved = true;
             dispatch({ t: "card.move", id, offset: { x: d.left + dx - at.x, y: d.top + dy - at.y } });
           }}
           onPointerUp={() => { drag.current = null; setDragging(false); }}
           onDoubleClick={(e) => { if (!(e.target as HTMLElement).closest("button")) dispatch({ t: "card.unpin", id }); }}>
        <b>{node.label}</b>
        <span className="file">{node.path?.split("/").slice(-2).join("/")}</span>
        <span className={`bd-badge ${changed ? "chg" : "ctx"}`}>{changed ? "Δ changed" : node.kind === "field" ? "field" : "context"}</span>
        <span className="sp" />
        <button className="bd-ibtn restore" title="Expand card" onClick={(e) => { e.stopPropagation(); dispatch({ t: "card.expand", id }); }}>⤢</button>
        <button className="bd-ibtn expand" title="Open full file" onClick={(e) => { e.stopPropagation(); onOpenFile(id); }}>⤢ Full file</button>
        <button className="bd-ibtn x" title="Close" aria-label={`Close ${node.label}`}
                onClick={(e) => { e.stopPropagation(); dispatch({ t: "card.close", id }); }}>✕</button>
      </div>
      {!collapsed && <CardBody node={node} {...rest} />}
    </div>
  );
}

type BodyProps = Pick<Props, "reviewId" | "board" | "sources" | "comments" | "onComments"> & { node: BoardNode };

function CardBody({ node, reviewId, board, sources, comments, onComments }: BodyProps) {
  const src = useEnsureSource(node.path, sources);
  const [lo, hi] = node.range ?? [0, 0];
  const pad = node.kind === "field" ? 4 : 0;
  const lines = useMemo(() => {
    if (isChange(src)) return sliceRange(lineDiff(src.before, src.after), lo - pad, hi + pad);
    if (src && "status" in src && src.status === "ok") return sliceRange(plainLines(src.file.text), lo - pad, hi + pad);
    return null;
  }, [src, lo, hi, pad]);
  const effects = board.impacts.filter((a) => a.node === node.id && a.severity === "warn");
  const touches = useMemo(() => {
    const own = board.impacts.find((a) => a.node === node.id);
    if (own) return own.text;
    const changed = new Map(board.nodes.filter((n) => n.change).map((n) => [n.id, n.label]));
    const e = board.edges.find((e) => e.src === node.id && changed.has(e.dst));
    return e ? `${e.kind === "call" || e.kind === "virtual" ? "calls" : e.kind} ${changed.get(e.dst)} (Δ)` : "context";
  }, [board, node.id]);
  return (
    <>
      {node.change ? (
        effects.length > 0 && <div className="effects">{effects.map((a, i) => <div key={i}><span className="ico">⚠</span>{a.text}</div>)}</div>
      ) : (
        <div className="fetched">⤓ fetched on demand · <b>p4 print {node.path}{src && "status" in src && src.status === "ok" && src.file.rev.startsWith("#") ? src.file.rev : ""}</b> · {touches}</div>
      )}
      {lines ? (
        <CodeView reviewId={reviewId} path={node.path!} lines={lines} mode="unified" anns={board.impacts}
                  comments={comments} onComments={onComments} />
      ) : src && "status" in src && src.status === "error" ? (
        <div className="bd-note error">{src.error} <button className="bd-ibtn" onClick={() => sources.reload(node.path!)}>Retry</button></div>
      ) : (
        <div className="bd-note">Fetching {node.path}…</div>
      )}
    </>
  );
}
