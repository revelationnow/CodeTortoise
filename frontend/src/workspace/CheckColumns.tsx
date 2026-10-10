import { type ReactNode, useRef, useState } from "react";
import { keys, save } from "../board/prefs";
import Resizer from "../board/Resizer";
import { CHECK_W, checkMax, loadCheckW } from "./layout";

/** The reading on the left and its To check column on the right, with a divider the reader drags (owner feedback
 * 2026-10-08 C on the story page, 2026-10-09 on the overview). One width, kept per browser, for every page that has it. */
export default function CheckColumns({ className = "", left, children }:
  { className?: string; left: ReactNode; children: ReactNode }) {
  const page = useRef<HTMLDivElement>(null);
  const [checkW, setCheckW] = useState(loadCheckW);
  return (
    <div className={`ov2 ov2-cols ${className}`.trim()} ref={page} style={{ ["--cw" as string]: `${checkW}px` }}>
      {left}
      <div className="ov2-check">
        <Resizer size={checkW} edge="left" min={CHECK_W.min} max={() => checkMax(page.current?.clientWidth ?? 0)}
                 onSize={setCheckW} onDone={(w) => save(keys.checkW, w)}
                 onReset={() => { setCheckW(CHECK_W.def); save(keys.checkW, CHECK_W.def); }} />
        {children}
      </div>
    </div>
  );
}
