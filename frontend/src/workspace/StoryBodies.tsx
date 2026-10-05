import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { StoryDetail } from "../board/types";
import { groupSites, OPEN_SITES } from "../stories/stories";
import { useWs } from "./context";
import NameText from "./NameText";

/** A repeated edit (change stories §3.2): its sites by directory and file, "Hide tests", and the functions with other
 * edits too; a site opens its file at the line in the detail panel. */
export function MechanicalStory({ detail }: { detail: StoryDetail }) {
  const ws = useWs();
  const [hide, setHide] = useState(false);
  const dirs = useMemo(() => groupSites(detail.sites, hide), [detail.sites, hide]);
  const tests = detail.sites.filter((s) => s.test).length;
  const openAll = detail.sites.length <= OPEN_SITES;
  const story = (sid: string, label: string) => (
    <Link to={ws.link(ws.item({ kind: "story", sid, view: "steps" }))} title={`Go to story ${sid}`} aria-label={`Go to story ${sid}`}>
      {label}<span className="ws-handle">{sid}</span></Link>
  );
  return (
    <div className="ws-mech">
      <div className="ws-tools">
        {tests > 0 && <label><input type="checkbox" checked={hide} onChange={(e) => setHide(e.target.checked)} /> Hide tests ({tests})</label>}
        {detail.also_in.length > 0 && (
          <span>Also in {detail.also_in.length} function{detail.also_in.length === 1 ? "" : "s"} with other edits:{" "}
            {detail.also_in.map((r, i) => <span key={r.node}>{i > 0 && ", "}{r.story ? story(r.story, r.label) : <b className="mono">{r.label}</b>}</span>)}</span>
        )}
      </div>
      {dirs.map((dir) => (
        <section key={dir.dir} className="ws-dir" aria-label={`Sites in ${dir.dir || "the root"}`}>
          <h3 className="mono">{dir.dir || "/"} <span className="muted small">{dir.count}</span></h3>
          {dir.files.map((f) => (
            <details key={f.path} open={openAll}>
              <summary><b className="mono">{f.name}</b> <span className="muted small">{f.sites.length} site{f.sites.length === 1 ? "" : "s"}</span></summary>
              <ul className="ws-sites">{f.sites.map((s, i) => (
                <li key={`${s.line}:${i}`}>
                  {s.path ? (
                    <Link className="ws-where" to={ws.link(ws.opened({ file: s.path, line: s.line }))}
                          title={`Open ${f.name} at line ${s.line}`} aria-label={`Open ${f.name} at line ${s.line}`}>
                      {s.function ?? "outside functions"} · line {s.line}</Link>
                  ) : <span className="ws-where">{s.function ?? "outside functions"} · line {s.line}</span>}
                  {s.test && <span className="ws-badge">test</span>}
                  <code className="del">− {s.before}</code>
                  <code className="add">+ {s.after}</code>
                  {s.effect && story(s.effect, "has an effect")}
                  {s.other_edits && story(s.other_edits, "other edits")}
                </li>
              ))}</ul>
            </details>
          ))}
        </section>
      ))}
    </div>
  );
}

/** The Tests story (change stories §3.3): test functions by file; each names the changed code it calls and opens its
 * code in the detail panel. */
export function TestsStory({ detail }: { detail: StoryDetail }) {
  const ws = useWs();
  const nodes = new Map(detail.board.nodes.map((n) => [n.id, n]));
  const byFile = new Map<string, typeof detail.functions>();
  for (const f of detail.functions) {
    const path = nodes.get(f.node)?.path ?? "(unknown file)";
    byFile.set(path, [...(byFile.get(path) ?? []), f]);
  }
  return (
    <div className="ws-tests">
      {[...byFile.entries()].map(([path, fns]) => (
        <section key={path} aria-label={`Tests in ${path}`}>
          <h3 className="mono">{path}</h3>
          <ul className="ws-steplist plain">{fns.map((f) => (
            <li key={f.node}>
              <Link to={ws.link(ws.opened({ node: f.node }))} title={`Open ${f.label}'s code`} aria-label={`Open ${f.label}'s code`}>
                <span className="ws-step-text"><b className="mono">{f.label}</b><span className="muted"><NameText text={f.note} /></span></span>
              </Link>
              {f.calls.length > 0 && (
                <div className="ws-calls">calls {f.calls.map((c, i) => (
                  <span key={c.node}>{i > 0 && ", "}<Link to={ws.link(c.story ? { ...ws.item({ kind: "story", sid: c.story, view: "steps" }), open: { node: c.node } }
                                                                        : ws.opened({ node: c.node }))}
                    className="ws-name" title={`Open ${c.label}'s code`} aria-label={`Open ${c.label}'s code`}>{c.label}</Link>
                    {c.story && <span className="ws-handle">{c.story}</span>}</span>
                ))}</div>
              )}
            </li>
          ))}</ul>
        </section>
      ))}
    </div>
  );
}
