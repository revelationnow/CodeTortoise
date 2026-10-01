import { dragSize, type Edge } from "./resize";

/** Drag handle on a panel edge (spec §2, §10). `size` may be a getter when the panel's current size is only known from
 * the DOM (e.g. an auto-height flow bar). Double-click calls `onReset`. */
export default function Resizer({ size, edge = "left", min, max, onSize, onDone, onReset }:
  { size: number | (() => number); edge?: Edge; min: number; max: () => number; onSize: (s: number) => void;
    onDone?: (s: number) => void; onReset?: () => void }) {
  return (
    <div className={`bd-resizer ${edge}`} title={onReset ? "Drag to resize · double-click to reset" : "Drag to resize"}
      onDoubleClick={onReset}
      onPointerDown={(e) => {
        e.preventDefault();
        const el = e.currentTarget, from = edge === "bottom" ? e.clientY : e.clientX;
        const start = typeof size === "function" ? size() : size, hi = max();
        el.setPointerCapture(e.pointerId);
        document.body.classList.add(edge === "bottom" ? "bd-resizing-v" : "bd-resizing");
        let s = start;
        const move = (ev: PointerEvent) => {
          s = dragSize(start, edge, from, edge === "bottom" ? ev.clientY : ev.clientX, min, hi);
          onSize(s);
        };
        const up = () => {
          el.removeEventListener("pointermove", move);
          el.removeEventListener("pointerup", up);
          document.body.classList.remove("bd-resizing", "bd-resizing-v");
          onDone?.(s);
        };
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerup", up);
      }} />
  );
}
