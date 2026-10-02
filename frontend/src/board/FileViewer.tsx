import { useEffect, useMemo, useRef } from "react";
import type { Comment } from "../api";
import CodeView from "./CodeView";
import { lineDiff, plainLines } from "./codeRows";
import type { Action, ViewerState } from "./reducer";
import Resizer from "./Resizer";
import type { Annotation } from "./types";
import { isChange, useEnsureSource, type useSources } from "./useSources";

type Sources = ReturnType<typeof useSources>;
interface Props {
  reviewId: number;
  viewer: ViewerState;
  dispatch: (a: Action) => void;
  sources: Sources;
  anns: Annotation[];
  comments: Comment[];
  onComments: () => void;
  width: number;
  onWidth: (w: number) => void;
  onWidthDone: (w: number) => void;
  /** Phone Files tab: fills its tab, no resize grip. */
  embedded?: boolean;
}

/** Stacked, collapsible full files (spec §3.5); newest on top, diff controls only for changed files. */
export default function FileViewer(p: Props) {
  const { viewer, dispatch } = p;
  const box = useRef<HTMLDivElement>(null);
  const reveal = viewer.reveal;
  useEffect(() => {                                     // scroll to the file / line just opened, flash its header
    if (!reveal || !box.current) return;
    const id = window.requestAnimationFrame(() => {
      const sec = box.current?.querySelector<HTMLElement>(`[data-path="${CSS.escape(reveal.path)}"]`);
      if (!sec) return;
      sec.classList.remove("flash");
      void sec.offsetWidth;
      sec.classList.add("flash");
      const target = (reveal.line && sec.querySelector<HTMLElement>(`[data-n="${reveal.line}"]`))
        || sec.querySelector<HTMLElement>(".bd-ln.a, .bd-ln.d, .bd-sbs .a, .bd-ann.warn") || sec;
      box.current!.scrollTop = target.getBoundingClientRect().top - box.current!.getBoundingClientRect().top + box.current!.scrollTop - 60;
    });
    return () => window.cancelAnimationFrame(id);
  }, [reveal]);
  return (
    <aside className={`bd-viewer${p.embedded ? " embedded" : ""}`} style={{ ["--w" as string]: `${p.width}px` }}>
      {!p.embedded && <Resizer size={p.width} edge="left" min={360} max={() => window.innerWidth * 0.75} onSize={p.onWidth}
                               onDone={p.onWidthDone} />}
      <div className="top">
        <b>Files</b><span className="muted">{viewer.files.length} open</span><span className="sp" />
        <span className="bd-seg">
          <button className={`bd-ibtn${viewer.mode === "unified" ? " on" : ""}`} onClick={() => dispatch({ t: "viewer.mode", mode: "unified" })}>Stacked</button>
          <button className={`bd-ibtn${viewer.mode === "split" ? " on" : ""}`} onClick={() => dispatch({ t: "viewer.mode", mode: "split" })}>Side by side</button>
        </span>
        <button className="bd-ibtn" onClick={() => dispatch({ t: "viewer.expandAll" })}>Expand all</button>
        <button className="bd-ibtn" onClick={() => dispatch({ t: "viewer.collapseAll" })}>Collapse all</button>
        <button className="bd-ibtn" onClick={() => dispatch({ t: "viewer.closeAll" })}>Close all</button>
      </div>
      <div className="files" ref={box}>
        {viewer.files.map((path) => (
          <FileSection key={path} {...p} path={path} collapsed={viewer.collapsed.includes(path)}
                       focus={reveal?.path === path ? reveal.line : null} />
        ))}
      </div>
    </aside>
  );
}

function FileSection({ path, collapsed, focus, viewer, dispatch, sources, reviewId, anns, comments, onComments }:
  Props & { path: string; collapsed: boolean; focus: number | null }) {
  const src = useEnsureSource(path, sources);
  const change = isChange(src) ? src : null;
  const lines = useMemo(() => {
    if (change) return lineDiff(change.before, change.after);
    if (src && "status" in src && src.status === "ok") return plainLines(src.file.text);
    return null;
  }, [src, change]);
  const counts = useMemo(() => lines && change ? [lines.filter((l) => l.t === "+").length, lines.filter((l) => l.t === "-").length] : null,
                         [lines, change]);
  const cls = change ? [...new Set(change.per_cl.map((c) => c.cl))] : [];
  return (
    <section className={`fsec${collapsed ? " collapsed" : ""}`} data-path={path}>
      <div className="hd" onClick={() => dispatch({ t: "viewer.toggle", path })}>
        <span className="chev">{collapsed ? "▸" : "▾"}</span><b>{path}</b>
        <span className="file">{change ? `CL ${cls.join(", ")}` : src && "status" in src && src.status === "ok"
          ? `unchanged · p4 print ${src.file.depot}${src.file.rev.startsWith("#") ? src.file.rev : ""}` : ""}</span>
        {counts && <span className="cnt"><span className="p">+{counts[0]}</span><span className="m">−{counts[1]}</span></span>}
        <span className="sp" />
        <button className="bd-ibtn x" title="Close file" aria-label={`Close ${path}`}
                onClick={(e) => { e.stopPropagation(); dispatch({ t: "viewer.close", path }); }}>✕</button>
      </div>
      {!collapsed && (lines ? (
        <CodeView reviewId={reviewId} path={path} lines={lines} mode={change && viewer.mode === "split" ? "split" : "unified"}
                  anns={anns} comments={comments} onComments={onComments} focus={focus} windowed />
      ) : src && "status" in src && src.status === "error" ? (
        <div className="bd-note error">{src.error} <button className="bd-ibtn" onClick={() => sources.reload(path)}>Retry</button></div>
      ) : <div className="bd-note">Fetching {path}…</div>)}
    </section>
  );
}
