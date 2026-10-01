/** Drag handle on a side panel's left edge (spec §2): width = start width + leftward drag, clamped. */
export default function Resizer({ width, min, maxFrac, onWidth, onDone }:
  { width: number; min: number; maxFrac: number; onWidth: (w: number) => void; onDone?: (w: number) => void }) {
  return (
    <div className="bd-resizer" title="Drag to resize" onPointerDown={(e) => {
      e.preventDefault();
      const el = e.currentTarget, startX = e.clientX;
      el.setPointerCapture(e.pointerId);
      document.body.classList.add("bd-resizing");
      let w = width;
      const move = (ev: PointerEvent) => {
        w = Math.round(Math.max(min, Math.min(window.innerWidth * maxFrac, width + (startX - ev.clientX))));
        onWidth(w);
      };
      const up = () => {
        el.removeEventListener("pointermove", move);
        el.removeEventListener("pointerup", up);
        document.body.classList.remove("bd-resizing");
        onDone?.(w);
      };
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
    }} />
  );
}
