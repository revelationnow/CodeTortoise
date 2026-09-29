import { useState } from "react";
import type { Comment, FileChange } from "../api";
import DiffView from "./DiffView";

interface Props { reviewId: number; files: FileChange[]; comments: Comment[]; onComments: () => void }

export default function Files({ reviewId, files, comments, onComments }: Props) {
  const [view, setView] = useState<string>("cumulative");
  const cls = [...new Set(files.flatMap((f) => f.per_cl.map((p) => p.cl)))].sort((a, b) => a - b);
  return (
    <div className="files">
      <div className="toolbar">
        <label>Diff <select value={view} onChange={(e) => setView(e.target.value)}>
          <option value="cumulative">cumulative (all CLs)</option>
          {cls.map((cl) => <option key={cl} value={String(cl)}>CL {cl} only</option>)}
        </select></label>
      </div>
      {files.map((f) => {
        const cl = view === "cumulative" ? null : Number(view);
        const step = cl === null ? null : f.per_cl.find((p) => p.cl === cl);
        if (cl !== null && !step) return null;
        return (
          <details key={f.depot} open className="card file">
            <summary><span className="mono">{f.depot}</span> <span className="badge">{f.action}</span>
              {f.base_rev && <span className="muted small"> base {f.base_rev}</span>}</summary>
            <DiffView reviewId={reviewId} depot={f.depot} cl={cl} before={step ? step.before : f.before}
                      after={step ? step.after : f.after} comments={comments} onComments={onComments} />
          </details>
        );
      })}
    </div>
  );
}
