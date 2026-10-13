import { type ReactNode, useRef, useState } from "react";
import { keys, save } from "../board/prefs";
import Resizer from "../board/Resizer";
import { useWs } from "./context";
import { CHECK_W, checkMax, loadCheckW } from "./layout";
import Strip, { FoldButton } from "./Strip";

/** The reading on the left and its To check column on the right, with a divider the reader drags (owner feedback
 * 2026-10-08 C on the story page, 2026-10-09 on the overview). One width, kept per browser, for every page that has it.
 * On a desktop the column folds to a strip named `foldName` (spec 2026-10-12 §3). */
export default function CheckColumns({ className = "", left, children, foldName }:
  { className?: string; left: ReactNode; children: ReactNode; foldName: string }) {
  const ws = useWs();
  const page = useRef<HTMLDivElement>(null);
  const [checkW, setCheckW] = useState(loadCheckW);
  const desktop = ws.screen === "desktop", folded = desktop && ws.folds.check;
  return (
    <div className={`ov2 ov2-cols${folded ? " check-folded" : ""} ${className}`.trim()} ref={page}
         style={{ ["--cw" as string]: `${checkW}px` }}>
      {left}
      {folded && <Strip name={foldName} label="To check" side="right" onUnfold={() => ws.setFold("check", false)} />}
      <div className="ov2-check" hidden={folded}>{/* hidden, not unmounted: an open comment box survives a fold */}
        <Resizer size={checkW} edge="left" min={CHECK_W.min} max={() => checkMax(page.current?.clientWidth ?? 0)}
                 onSize={setCheckW} onDone={(w) => save(keys.checkW, w)}
                 onReset={() => { setCheckW(CHECK_W.def); save(keys.checkW, CHECK_W.def); }} />
        {desktop && <FoldButton label="To check" side="right" onFold={() => ws.setFold("check", true)} />}
        {children}
      </div>
    </div>
  );
}
