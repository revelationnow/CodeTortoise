import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { keys, loadWidth, save } from "../board/prefs";
import Resizer from "../board/Resizer";
import { api, ApiError, type NodeName } from "../api";
import type { Board, StoryDetail } from "../board/types";
import { at } from "./address";
import { useWs } from "./context";
import { short } from "./crumbs";
import { detailBoards, locateNode } from "./detail";
import FileDiff from "./FileDiff";
import FunctionCode from "./FunctionCode";
import Neighbours from "./Neighbours";

/** The detail panel (spec 2026-10-04-review-workspace §3.7): a node's code or a file's diff, opened on demand; on a
 * phone a full-screen sheet whose top bar names its item. */
export default function Detail() {
  const ws = useWs(), d = ws.data, open = ws.addr.open!;
  const [width, setWidth] = useState(() => Math.max(320, loadWidth(keys.detailW, Math.round(window.innerWidth * 0.45))));
  const nid = "node" in open ? open.node : null, known = nid ? d.names[nid] : null;
  // a node off every board (a Neighbours row's caller or callee) is named by its neighbours (§4.3); null: no such node
  const [asked, setAsked] = useState<{ nid: string; name: NodeName | null; error?: string } | null>(null);
  useEffect(() => {
    if (!nid || known) return;
    let live = true;
    api.neighbours(d.id, nid, 1).then((m) => { if (live) setAsked({ nid, name: m.node }); }, (e) => {
      if (live) setAsked({ nid, name: null, error: e instanceof ApiError && e.status === 404 ? undefined : String(e.message ?? e) });
    });
    return () => { live = false; };
  }, [nid, known, d.id]);
  const off = asked?.nid === nid ? asked : null, name = known ?? off?.name ?? null;
  const [story, setStory] = useState<{ sid: string; detail: StoryDetail | null } | null>(null);   // null detail: failed
  const [full, setFull] = useState(false);
  const { story: storyOf, id: rid } = d;
  useEffect(() => {
    const sid = name?.story;
    if (!sid) return;
    let live = true;
    storyOf(sid).then((s) => { if (live) setStory({ sid, detail: s }); }, () => { if (live) setStory({ sid, detail: null }); });
    return () => { live = false; };
  }, [name?.story, storyOf]);
  const own = story && story.sid === name?.story ? story : null;
  // the place being read: a field or context function off its own story is drawn there (a story's graph, a cluster)
  const place = ws.addr.place, hereKey = place.kind === "story" ? `s:${place.sid}` : place.kind === "cluster" ? `c:${place.cid}` : null;
  const [here, setHere] = useState<{ key: string; at: StoryDetail | Board } | null>(null);
  useEffect(() => {
    if (!nid || !hereKey) return;
    let live = true;
    const id = hereKey.slice(2);
    (hereKey.startsWith("s:") ? storyOf(id) : api.board(rid, id))
      .then((at) => { if (live) setHere({ key: hereKey, at }); }).catch(() => {});
    return () => { live = false; };
  }, [nid, hereKey, storyOf, rid]);
  const close = ws.link({ ...ws.addr, open: null, tab: "diff" });
  const found = nid ? locateNode(nid, detailBoards(own?.detail ?? null, here?.key === hereKey ? here.at : null, d.board)) : null;
  // until the node's story has answered, a node without its lines may yet get them: wait rather than show the file first
  const waiting = !!name?.story && !own && !(found?.node.path && found.node.range);
  const node = found?.node;
  const path = "file" in open ? open.file : node?.path ?? name?.path ?? null;
  const label = "file" in open ? path!.slice(path!.lastIndexOf("/") + 1) : node?.label ?? name?.label ?? null;
  const lines = node?.range ? `lines ${node.range[0]}–${node.range[1]}` : "file" in open && open.line ? `line ${open.line}`
    : name?.line ? `line ${name.line}` : null;
  const badge = !nid ? null : node?.kind === "field" || node?.kind === "struct" || name?.kind === "field" ? "field"
    : node?.change ? "changed" : "context";
  const sid = name?.story ?? null, st = sid ? d.stories?.stories.find((s) => s.id === sid) : null;
  const anns = found?.board.impacts ?? own?.detail?.board.impacts ?? d.board?.impacts ?? [];
  const wide = ws.screen === "desktop" && width > 900;

  const body = () => {
    if (nid && !name && !node && !off) return <div className="bd-note">Finding this function…</div>;
    if (nid && !name && !node && off?.error) return <div className="bd-note error">{off.error}</div>;
    if (nid && !name && !node)
      return <div className="banner warn">This function isn't in this review. <Link to={ws.link(at({ kind: "whole" }))}>Whole change</Link></div>;
    if (waiting) return <div className="bd-note">Fetching {label}'s code…</div>;
    if (node?.path && node.range && !full) return <FunctionCode node={node} board={found!.board} />;
    if (!path) return <p className="muted">No code to show for {label}.</p>;
    const line = "file" in open ? open.line : node?.range?.[0] ?? name?.line ?? null;
    return <FileDiff key={path} path={path} line={line} anns={anns} wide={wide}
                     cl={ws.addr.place.kind === "cl" ? ws.addr.place.cl : null} />;
  };
  return (
    <aside className="ws-detail" style={{ ["--w" as string]: `${width}px` }} aria-label={`Code: ${label ?? "not found"}`}>
      {ws.screen === "desktop" && <Resizer size={width} edge="left" min={320} max={() => window.innerWidth * 0.75}
                                           onSize={setWidth} onDone={(w) => save(keys.detailW, w)} />}
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
        {nid && (name || node) && (
          <div className="ws-tabs" role="tablist" aria-label="Detail">
            {(["diff", "neighbours"] as const).map((t) => (
              <Link key={t} id={`ws-tab-${t}`} role="tab" aria-selected={ws.addr.tab === t} aria-controls="ws-tabpanel"
                    className={ws.addr.tab === t ? "on" : ""} replace to={ws.link({ ...ws.addr, tab: t })}>
                {t === "diff" ? "Diff" : "Neighbours"}</Link>
            ))}
          </div>
        )}
        {node?.path && node.range && ws.addr.tab === "diff" && (
          <div className="ws-detail-tools">
            <span className="bd-seg">
              <button className={`bd-ibtn${!full ? " on" : ""}`} aria-pressed={!full} onClick={() => setFull(false)}>Function</button>
              <button className={`bd-ibtn${full ? " on" : ""}`} aria-pressed={full} onClick={() => setFull(true)}>Full file</button>
            </span>
          </div>
        )}
      </div>
      <div className="ws-detail-body" {...(nid && (name || node)
        ? { id: "ws-tabpanel", role: "tabpanel", "aria-labelledby": `ws-tab-${ws.addr.tab}` } : {})}>
        {nid && ws.addr.tab === "neighbours" && (name || node) ? <Neighbours nid={nid} /> : body()}</div>
    </aside>
  );
}
