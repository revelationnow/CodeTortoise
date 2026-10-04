import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Comment } from "../api";
import { CardBody } from "../board/CardLayer";
import type { StoryDetail } from "../board/types";
import type { useSources } from "../board/useSources";
import { Ticks } from "./StoryList";
import { groupSites, OPEN_SITES } from "./stories";

/** A repeated edit (spec 2026-10-04-change-stories §3.2): its sites by directory and file, a "Hide tests" filter and
 * the functions that have other edits too. */
export function MechanicalStory({ reviewId, detail }: { reviewId: number; detail: StoryDetail }) {
  const [hide, setHide] = useState(false);
  const dirs = useMemo(() => groupSites(detail.sites, hide), [detail.sites, hide]);
  const tests = detail.sites.filter((s) => s.test).length;
  const openAll = detail.sites.length <= OPEN_SITES;
  return (
    <div className="st-mech">
      <div className="st-tools">
        {tests > 0 && <label><input type="checkbox" checked={hide} onChange={(e) => setHide(e.target.checked)} /> Hide tests ({tests})</label>}
        {detail.also_in.length > 0 && (
          <span>Also in {detail.also_in.length} function{detail.also_in.length === 1 ? "" : "s"} with other edits:{" "}
            {detail.also_in.map((r, i) => (
              <span key={r.node}>{i > 0 && ", "}{r.story ? <Link to={`/r/${reviewId}/s/${r.story}`}>{r.label} ({r.story})</Link> : r.label}</span>
            ))}</span>
        )}
      </div>
      {dirs.map((d) => (
        <section key={d.dir} className="st-dir" aria-label={`Sites in ${d.dir || "the root"}`}>
          <h3>{d.dir || "/"} <span className="muted small">{d.count}</span></h3>
          {d.files.map((f) => (
            <details key={f.path} open={openAll}>
              <summary><b>{f.name}</b> <span className="muted small">{f.sites.length} site{f.sites.length === 1 ? "" : "s"}</span></summary>
              <ul className="st-sites">
                {f.sites.map((s) => (
                  <li key={`${s.line}`}>
                    <span className="st-where">{s.function ?? "outside functions"} · line {s.line}{s.test && <span className="bd-pill ghost">test</span>}</span>
                    <code className="del">− {s.before}</code>
                    <code className="add">+ {s.after}</code>
                    {s.effect && <Link to={`/r/${reviewId}/s/${s.effect}`}>has an effect ›</Link>}
                    {s.other_edits && <Link to={`/r/${reviewId}/s/${s.other_edits}`}>other edits in {s.other_edits} ›</Link>}
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </section>
      ))}
    </div>
  );
}

interface TestsProps {
  reviewId: number;
  detail: StoryDetail;
  sources: ReturnType<typeof useSources>;
  comments: Comment[];
  onComments: () => void;
}

/** The Tests story (spec §3.3): test functions by file with their diffs; each names the changed code it calls. */
export function TestsStory({ reviewId, detail, sources, comments, onComments }: TestsProps) {
  const [open, setOpen] = useState<string | null>(null);
  const nodes = useMemo(() => new Map(detail.board.nodes.map((n) => [n.id, n])), [detail.board]);
  const byFile = new Map<string, typeof detail.functions>();
  for (const f of detail.functions) {
    const path = nodes.get(f.node)?.path ?? "(unknown file)";
    byFile.set(path, [...(byFile.get(path) ?? []), f]);
  }
  return (
    <div className="st-tests">
      {[...byFile.entries()].map(([path, fns]) => (
        <section key={path} aria-label={`Tests in ${path}`}>
          <h3>{path}</h3>
          <ul>
            {fns.map((f) => {
              const n = nodes.get(f.node);
              return (
                <li key={f.node} className={open === f.node ? "open" : ""}>
                  <div className="ph-head" onClick={() => n?.path && setOpen(open === f.node ? null : f.node)}>
                    <div className="ph-text"><b>{f.label}</b><span className="ph-reason"><Ticks text={f.note} /></span></div>
                    {n?.path && <span className="ph-caret">{open === f.node ? "▾" : "▸"}</span>}
                  </div>
                  {f.calls.length > 0 && (
                    <div className="st-calls">calls {f.calls.map((c, i) => (
                      <span key={c.node}>{i > 0 && ", "}{c.story ? <Link to={`/r/${reviewId}/s/${c.story}?node=${c.node}`}>{c.label} ({c.story})</Link> : c.label}</span>
                    ))}</div>
                  )}
                  {open === f.node && n && (
                    <div className="ph-code">
                      <CardBody node={n} reviewId={reviewId} board={detail.board} sources={sources} comments={comments} onComments={onComments} />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
