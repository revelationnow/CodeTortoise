import { useEffect, useMemo, useRef, useState } from "react";
import type { Comment } from "../api";
import CodeView from "../board/CodeView";
import { lineDiff, plainLines } from "../board/codeRows";
import { expandRange, foldRuns, type Range, revealRange } from "../board/fold";
import { keys, loadViewerView, save, type ViewerView } from "../board/prefs";
import type { Annotation } from "../board/types";
import { isChange, useEnsureSource } from "../board/useSources";
import Explain, { FileSummaryView } from "../components/Explain";
import { useAi } from "../lib/ai";
import { onLine } from "../lib/anchors";
import { useWs } from "./context";

interface Props {
  path: string;
  /** A line to show (and open if it is folded). */
  line: number | null;
  anns: Annotation[];
  /** The changelist to show first (a CL page's files); null: all together. */
  cl?: number | null;
  wide: boolean;
}

/** One file in the detail panel (spec 2026-10-04-review-workspace §3.7; was the stacked file viewer): its diff, changes
 * only or the full file, per changelist, with folding, notes and line comments. */
export default function FileDiff({ path, line, anns, cl: firstCl = null, wide }: Props) {
  const ws = useWs(), d = ws.data;
  const src = useEnsureSource(path, ws.sources);
  const change = isChange(src) ? src : null;
  const cls = change ? [...new Set(change.per_cl.map((c) => c.cl))] : [];
  const [cl, setCl] = useState<number | null>(firstCl !== null && cls.includes(firstCl) ? firstCl : null);
  const [view, setView] = useState<ViewerView>(loadViewerView);
  const [chosen, setMode] = useState<"unified" | "split" | null>(null);      // until the reader picks, the panel's width does
  const mode = chosen ?? (wide ? "split" : "unified");
  const [shown, setShown] = useState<Range[]>([]);
  const box = useRef<HTMLDivElement>(null);
  const step = change && cl !== null ? change.per_cl.find((x) => x.cl === cl) ?? null : null;
  const lines = useMemo(() => {
    if (change) return step ? lineDiff(step.before, step.after) : lineDiff(change.before, change.after);
    if (src && "status" in src && src.status === "ok") return plainLines(src.file.text);
    return null;
  }, [src, change, step]);
  const mine = useMemo(() => anns.filter((x) => x.path === path && x.side === "new"), [anns, path]);
  const keep = useMemo(() => {                      // lines with notes or comment threads stay in the changes view
    if (!lines) return new Set<number>();
    const ns = new Set<number>([...mine.map((x) => x.line), ...d.comments.filter((c) => threadOn(c, path, cl)).map((c) => c.anchor.line as number)]);
    return new Set(lines.flatMap((l, i) => (l.n !== null && ns.has(l.n) ? [i] : [])));
  }, [lines, mine, d.comments, path, cl]);
  useEffect(() => setShown([]), [cl]);
  useEffect(() => {                                 // a folded line asked for opens the lines around it
    if (line && lines) { const r = revealRange(lines, line); if (r) setShown((s) => [...s, r]); }
  }, [line, lines]);
  useEffect(() => {                                 // and is scrolled to once drawn
    if (!line || !lines) return;
    const id = window.requestAnimationFrame(() => box.current?.querySelector(`[data-n="${line}"]`)?.scrollIntoView({ block: "center" }));
    return () => window.cancelAnimationFrame(id);
  }, [line, lines, view]);
  const folding = !!change && view === "changes";
  const runs = useMemo(() => (folding && lines ? foldRuns(lines, shown, keep) : null), [folding, lines, shown, keep]);
  const counts = lines && change ? [lines.filter((l) => l.t === "+").length, lines.filter((l) => l.t === "-").length] : null;
  const summarised = useAi()?.view?.file_summaries[path]?.summary;
  return (
    <div className="ws-file" ref={box}>
      <div className="ws-file-tools">
        {change ? <span className="act">{change.action}</span> : src && "status" in src && src.status === "ok"
          ? <span className="muted small">unchanged · {src.file.depot}{src.file.rev.startsWith("#") ? src.file.rev : ""}</span> : null}
        {change?.base_rev && <span className="muted small">base {change.base_rev}</span>}
        {counts && <span className="cnt"><span className="p">+{counts[0]}</span> <span className="m">−{counts[1]}</span></span>}
        <span className="sp" />
        {change && <Explain kind="file" target={path} label="Summarise" has={!!summarised} />}
        {change && cls.length > 0 && (
          <select aria-label="Changelist" value={cl === null ? "all" : String(cl)}
                  onChange={(e) => setCl(e.target.value === "all" ? null : Number(e.target.value))}>
            <option value="all">All CLs</option>
            {cls.map((c) => <option key={c} value={String(c)}>CL {c}</option>)}
          </select>
        )}
        {change && (
          <span className="bd-seg">
            <button className={`bd-ibtn${view === "changes" ? " on" : ""}`} aria-pressed={view === "changes"}
                    onClick={() => { setView("changes"); save(keys.viewerView, "changes"); }}>Changes</button>
            <button className={`bd-ibtn${view === "full" ? " on" : ""}`} aria-pressed={view === "full"}
                    onClick={() => { setView("full"); save(keys.viewerView, "full"); }}>Full file</button>
          </span>
        )}
        {change && (
          <span className="bd-seg">
            <button className={`bd-ibtn${mode === "unified" ? " on" : ""}`} aria-pressed={mode === "unified"} onClick={() => setMode("unified")}>Stacked</button>
            <button className={`bd-ibtn${mode === "split" ? " on" : ""}`} aria-pressed={mode === "split"} onClick={() => setMode("split")}>Side by side</button>
          </span>
        )}
      </div>
      {change && <FileSummaryView path={path} />}
      {lines ? (
        <CodeView reviewId={d.id} path={path} lines={lines} mode={change ? mode : "unified"} anns={anns} comments={d.comments}
                  onComments={d.loadComments} focus={line} windowed cl={cl} runs={runs}
                  onExpand={(run, how) => setShown((s) => [...s, expandRange(run, how)])} />
      ) : src && "status" in src && src.status === "error" ? (
        <div className="bd-note error">{src.error} <button className="bd-ibtn" onClick={() => ws.sources.reload(path)}>Retry</button></div>
      ) : <div className="bd-note">Fetching {path}…</div>}
    </div>
  );
}

/** A root line comment on this file's new side, for the changelist in view. */
function threadOn(c: Comment, path: string, cl: number | null): boolean {
  return c.anchor_kind === "line" && c.parent_id === null && c.anchor.side === "new" && onLine(c, path, "new", c.anchor.line as number, cl);
}
