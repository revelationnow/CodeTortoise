import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Comment } from "../api";
import Explain, { FileSummaryView } from "../components/Explain";
import { useAi } from "../lib/ai";
import { onLine } from "../lib/anchors";
import CodeView from "./CodeView";
import { lineDiff, plainLines } from "./codeRows";
import { expandRange, foldRuns, type Range, revealRange } from "./fold";
import { keys, loadViewerView, save, type ViewerView } from "./prefs";
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
  const [cl, setCl] = useState<number | null>(null);               // null: all changelists together
  const [view, setView] = useState<ViewerView>(loadViewerView);     // changed files: changes only, or the full file
  const [shown, setShown] = useState<Range[]>([]);                  // folded runs opened by the reader
  const sec = useRef<HTMLElement>(null);
  const keepAt = useRef<{ line: number; offset: number } | null>(null);
  const step = change && cl !== null ? change.per_cl.find((x) => x.cl === cl) ?? null : null;
  const lines = useMemo(() => {
    if (change) return step ? lineDiff(step.before, step.after) : lineDiff(change.before, change.after);
    if (src && "status" in src && src.status === "ok") return plainLines(src.file.text);
    return null;
  }, [src, change, step]);
  const mine = useMemo(() => anns.filter((x) => x.path === path && x.side === "new"), [anns, path]);
  const keep = useMemo(() => {                       // lines with notes or comment threads stay in the changes view
    if (!lines) return new Set<number>();
    const ns = new Set<number>([...mine.map((x) => x.line),
      ...comments.filter((c) => c.anchor_kind === "line" && c.parent_id === null && onLineAny(c, path, cl)).map((c) => c.anchor.line as number)]);
    return new Set(lines.flatMap((l, i) => (l.n !== null && ns.has(l.n) ? [i] : [])));
  }, [lines, mine, comments, path, cl]);
  useEffect(() => setShown([]), [cl]);
  useEffect(() => {                                  // opening the file at a folded line opens the lines around it
    if (focus && lines) {
      const r = revealRange(lines, focus);
      if (r) setShown((s) => [...s, r]);
    }
  }, [focus, lines]);
  const folding = !!change && view === "changes";
  const runs = useMemo(() => (folding && lines ? foldRuns(lines, shown, keep) : null), [folding, lines, shown, keep]);
  useLayoutEffect(() => {                            // after a view switch, put the remembered line back where it was
    const k = keepAt.current, box = sec.current?.closest<HTMLElement>(".files");
    if (!k || !box) return;
    keepAt.current = null;
    const row = sec.current?.querySelector<HTMLElement>(`[data-n="${k.line}"]`);
    if (row) box.scrollTop += row.getBoundingClientRect().top - box.getBoundingClientRect().top - k.offset;
  });
  const switchView = (v: ViewerView) => {
    const box = sec.current?.closest<HTMLElement>(".files");
    const top = box?.getBoundingClientRect().top ?? 0;
    const row = [...(sec.current?.querySelectorAll<HTMLElement>("[data-n]") ?? [])]
      .find((r) => r.getBoundingClientRect().bottom > top + 1);             // the first line in view
    if (row && lines) {
      const line = Number(row.dataset.n);
      keepAt.current = { line, offset: Math.max(0, row.getBoundingClientRect().top - top) };
      const r = revealRange(lines, line);
      if (v === "changes" && r) setShown((s) => [...s, r]);
    }
    setView(v);
    save(keys.viewerView, v);
  };
  const counts = useMemo(() => lines && change ? [lines.filter((l) => l.t === "+").length, lines.filter((l) => l.t === "-").length] : null,
                         [lines, change]);
  const cls = change ? [...new Set(change.per_cl.map((c) => c.cl))] : [];
  const summarised = useAi()?.view?.file_summaries[path]?.summary;
  return (
    <section ref={sec} className={`fsec${collapsed ? " collapsed" : ""}`} data-path={path}>
      <div className="hd" onClick={() => dispatch({ t: "viewer.toggle", path })}>
        <span className="chev">{collapsed ? "▸" : "▾"}</span><b>{path}</b>
        {change && <span className="act">{change.action}</span>}
        {change && change.base_rev && <span className="file">base {change.base_rev}</span>}
        <span className="file">{change ? "" : src && "status" in src && src.status === "ok"
          ? `unchanged · p4 print ${src.file.depot}${src.file.rev.startsWith("#") ? src.file.rev : ""}` : ""}</span>
        {counts && <span className="cnt"><span className="p">+{counts[0]}</span><span className="m">−{counts[1]}</span></span>}
        <span className="sp" />
        {change && <Explain kind="file" target={path} label="Summarise" has={!!summarised} />}
        {change && (
          <span className="bd-file-tools" onClick={(e) => e.stopPropagation()}>
            <select aria-label="Changelist" value={cl === null ? "all" : String(cl)}
                    onChange={(e) => setCl(e.target.value === "all" ? null : Number(e.target.value))}>
              <option value="all">All CLs</option>
              {cls.map((c) => <option key={c} value={String(c)}>CL {c}</option>)}
            </select>
            <span className="bd-seg">
              <button className={`bd-ibtn${view === "changes" ? " on" : ""}`} onClick={() => switchView("changes")}>Changes</button>
              <button className={`bd-ibtn${view === "full" ? " on" : ""}`} onClick={() => switchView("full")}>Full file</button>
            </span>
          </span>
        )}
        <button className="bd-ibtn x" title="Close file" aria-label={`Close ${path}`}
                onClick={(e) => { e.stopPropagation(); dispatch({ t: "viewer.close", path }); }}>✕</button>
      </div>
      {!collapsed && change && <FileSummaryView path={path} />}
      {!collapsed && (lines ? (
        <CodeView reviewId={reviewId} path={path} lines={lines} mode={change && viewer.mode === "split" ? "split" : "unified"}
                  anns={anns} comments={comments} onComments={onComments} focus={focus} windowed cl={cl}
                  runs={runs} onExpand={(run, how) => setShown((s) => [...s, expandRange(run, how)])} />
      ) : src && "status" in src && src.status === "error" ? (
        <div className="bd-note error">{src.error} <button className="bd-ibtn" onClick={() => sources.reload(path)}>Retry</button></div>
      ) : <div className="bd-note">Fetching {path}…</div>)}
    </section>
  );
}

/** A root line comment on this file, on either side, for the changelist in view (null: all changelists). */
function onLineAny(c: Comment, path: string, cl: number | null): boolean {
  const side = c.anchor.side as "new" | "old", line = c.anchor.line as number;
  return side === "new" && onLine(c, path, side, line, cl);
}
