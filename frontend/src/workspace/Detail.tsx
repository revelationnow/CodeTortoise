import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { load, save } from "../board/prefs";
import Resizer from "../board/Resizer";
import type { StoryDetail } from "../board/types";
import { at } from "./address";
import { useWs } from "./context";
import { short } from "./crumbs";
import { locateNode } from "./detail";
import FileDiff from "./FileDiff";
import FunctionCode from "./FunctionCode";

const WIDTH_KEY = "ct.ws.detailW";

/** The detail panel (spec 2026-10-04-review-workspace §3.7): a node's code or a file's diff, opened on demand; on a
 * phone a full-screen sheet whose top bar names its item. */
export default function Detail() {
  const ws = useWs(), d = ws.data, open = ws.addr.open!;
  const [width, setWidth] = useState(() => {
    const w = load<unknown>(WIDTH_KEY, 0);
    return typeof w === "number" && w >= 320 && w <= 4000 ? w : Math.round(window.innerWidth * 0.45);
  });
  const nid = "node" in open ? open.node : null, name = nid ? d.names[nid] : null;
  const [story, setStory] = useState<StoryDetail | null>(null);
  const [full, setFull] = useState(false);
  useEffect(() => {
    if (!name?.story) return;
    let live = true;
    d.story(name.story).then((s) => { if (live) setStory(s); }).catch(() => {});
    return () => { live = false; };
  }, [name?.story, d]);
  const close = ws.link({ ...ws.addr, open: null, tab: "diff" });
  const found = nid ? locateNode(nid, [story?.graph, story?.board, d.board]) : null;
  const node = found?.node;
  const path = "file" in open ? open.file : node?.path ?? name?.path ?? null;
  const label = "file" in open ? path!.slice(path!.lastIndexOf("/") + 1) : node?.label ?? name?.label ?? null;
  const lines = node?.range ? `lines ${node.range[0]}–${node.range[1]}` : "file" in open && open.line ? `line ${open.line}`
    : name?.line ? `line ${name.line}` : null;
  const badge = !nid ? null : node?.kind === "field" || node?.kind === "struct" || name?.kind === "field" ? "field"
    : node?.change ? "changed" : "context";
  const sid = name?.story ?? null, st = sid ? d.stories?.stories.find((s) => s.id === sid) : null;
  const anns = found?.board.impacts ?? story?.board.impacts ?? d.board?.impacts ?? [];
  const wide = ws.screen === "desktop" && width > 900;

  const body = () => {
    if (nid && !name && !node)
      return <div className="banner warn">This function isn't in this review. <Link to={ws.link(at({ kind: "whole" }))}>Whole change</Link></div>;
    if (node?.path && node.range && !full) return <FunctionCode node={node} board={found!.board} />;
    if (!path) return <p className="muted">No code to show for {label}.</p>;
    const line = "file" in open ? open.line : node?.range?.[0] ?? name?.line ?? null;
    return <FileDiff key={path} path={path} line={line} anns={anns} wide={wide}
                     cl={ws.addr.place.kind === "cl" ? ws.addr.place.cl : null} />;
  };
  return (
    <aside className="ws-detail" style={{ ["--w" as string]: `${width}px` }} aria-label={`Code: ${label ?? "not found"}`}>
      {ws.screen === "desktop" && <Resizer size={width} edge="left" min={320} max={() => window.innerWidth * 0.75}
                                           onSize={setWidth} onDone={(w) => save(WIDTH_KEY, w)} />}
      {ws.screen === "phone" && (
        <div className="ws-phonebar">
          <Link to={close} aria-label="Close the code" title="Close the code">‹ {st ? st.id : "Back"}</Link>
          <span className="sep" aria-hidden>·</span><b>{label}</b>
        </div>
      )}
      <div className="ws-detail-head">
        <div className="ws-detail-name">
          <b className="mono">{label ?? "Not found"}</b>
          {badge && <span className={`ws-badge ${badge}`}>{badge}</span>}
          {st && <Link className="ws-detail-story" to={ws.link(ws.item({ kind: "story", sid: st.id, view: "steps" }))}
                       title={`Go to story ${st.id}: ${short(st.title)}`} aria-label={`Go to story ${st.id}: ${short(st.title)}`}>
            {short(st.title, 40)}<span className="ws-handle">{st.id}</span></Link>}
          {ws.screen !== "phone" && <Link className="ws-x" to={close} aria-label="Close the code" title="Close the code">✕</Link>}
        </div>
        {path && <div className="ws-detail-path mono">{path}{lines && <span className="muted"> · {lines}</span>}</div>}
        {node?.path && node.range && (
          <div className="ws-detail-tools">
            <span className="bd-seg">
              <button className={`bd-ibtn${!full ? " on" : ""}`} aria-pressed={!full} onClick={() => setFull(false)}>Function</button>
              <button className={`bd-ibtn${full ? " on" : ""}`} aria-pressed={full} onClick={() => setFull(true)}>Full file</button>
            </span>
          </div>
        )}
      </div>
      <div className="ws-detail-body">{body()}</div>
    </aside>
  );
}
