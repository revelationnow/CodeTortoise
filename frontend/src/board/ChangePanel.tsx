import { useState } from "react";
import type { Comment } from "../api";
import Comments from "../components/Comments";
import type { Action } from "./reducer";
import Resizer from "./Resizer";
import type { About } from "./types";

interface Props {
  reviewId: number;
  comments: Comment[];
  onComments: () => void;
  layers: { level: number; name: string }[];
  about: About;
  risk: string | null;
  openFiles: string[];
  dispatch: (a: Action) => void;
  wide: boolean;
  width: number;
  onWidth: (w: number) => void;
  onWidthDone: (w: number) => void;
}

/** "What's this change?" (spec §3.6): files tree first, then intent, why it's risky, changelists. Pushes the board. */
export default function ChangePanel({ reviewId, comments, onComments, layers, about, risk, openFiles, dispatch, wide, width, onWidth,
  onWidthDone }: Props) {
  const [shut, setShut] = useState<Set<string>>(new Set());
  const nFiles = about.tree.reduce((n, d) => n + d.files.length, 0);
  return (
    <aside className="bd-about" style={{ ["--w" as string]: `${width}px` }}>
      <Resizer width={width} min={280} maxFrac={0.6} onWidth={onWidth} onDone={onWidthDone} />
      <div className="top">
        <button className="bd-ibtn close" title="Close" aria-label="Close change summary" onClick={() => dispatch({ t: "about.toggle", open: false })}>✕</button>
        {risk && <span className={`bd-pill ${risk}`}>{risk.toUpperCase()} RISK</span>}
        <h2>What this change is trying to do</h2>
        <p>{about.cls.map((c) => `CL ${c.cl}`).join(" · ")} · {nFiles} files · {about.intent_source === "llm"
          ? "summarised from the CL descriptions, the diff and the analysis" : "from the CL descriptions and the analysis"}</p>
      </div>
      <div className="body">
        {about.drift.length > 0 && (
          <div className="bd-drift">
            ⚠ The base workspace is not at the changelists' base revision, so context code fetched from it may not match
            what was analysed: {about.drift.join("; ")}
          </div>
        )}
        <h3>Files in this change</h3>
        <div className="tree">
          {about.tree.map((d) => (
            <div key={d.dir}>
              <div className="dir" onClick={() => setShut((s) => { const n = new Set(s); if (n.has(d.dir)) n.delete(d.dir); else n.add(d.dir); return n; })}>
                <span className="caret">{shut.has(d.dir) ? "▸" : "▾"}</span>📁 {d.dir}/
              </div>
              {!shut.has(d.dir) && d.files.map((f) => (
                <div key={f.path} className={`file${openFiles.includes(f.path) ? " on" : ""}`}
                     onClick={() => dispatch({ t: "viewer.open", path: f.path, wide })}>
                  📄 {f.name}<span className="act">{f.action}</span>
                  {f.cls.length > 0 && <span className="clb">CL {f.cls.join(", ")}</span>}
                  <span className="cnt"><span className="p">+{f.add}</span><span className="m">−{f.rem}</span></span>
                </div>
              ))}
            </div>
          ))}
        </div>
        <h3>Intent</h3>
        <div className="intent">{about.intent}</div>
        {about.why.length > 0 && <>
          <h3>Why it's {risk ?? "flagged"} risk</h3>
          <ul className="why">{about.why.map((w) => <li key={w.finding}><span className={`sev ${w.severity}`}>{w.severity.toUpperCase()}</span>{w.text}</li>)}</ul>
        </>}
        <h3>Discussion</h3>
        <Comments reviewId={reviewId} comments={comments} kind="review" anchor={{}} onChange={onComments} />
        {[...new Set(comments.filter((c) => c.anchor_kind === "chapter" && c.parent_id === null).map((c) => c.anchor.level as number | null))]
          .map((level) => (
            <div key={String(level)} className="bd-layer-thread">
              <div className="m">Layer {layers.find((l) => l.level === level)?.name ?? (level === null ? "unlayered" : `L${level}`)}</div>
              <Comments reviewId={reviewId} comments={comments} kind="chapter" anchor={{ level }} onChange={onComments} compact />
            </div>
          ))}
        <h3>Changelists</h3>
        {about.cls.map((c) => (
          <div key={c.cl} className="cl"><span className="n">CL {c.cl}</span> <span className="m">· {c.user} · {c.files} files</span>
            <div className="desc">{c.description}</div></div>
        ))}
      </div>
    </aside>
  );
}
