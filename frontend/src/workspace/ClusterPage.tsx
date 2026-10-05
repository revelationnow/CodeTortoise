import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type Board } from "../api";
import { stepCluster } from "../board/overview";
import { useWs } from "./context";
import { short } from "./crumbs";
import { pickFlow } from "./flows";
import GraphView from "./graph/GraphView";
import { Ticks } from "./NameText";

/** One part of a split review (spec 2026-10-04-review-workspace §3.5): name, layer, risk, counts, ‹ ›, the stories it
 * holds, then its graph with the flow strip. Visitors link to their own part. */
export default function ClusterPage({ cid }: { cid: string }) {
  const ws = useWs(), d = ws.data, ov = d.overview!;
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api.board(d.id, cid).then((b) => { if (live) { setBoard(b); setError(null); } })
      .catch((e) => { if (live) setError(e instanceof ApiError && e.status === 404 ? e.message : String(e.message ?? e)); });
    return () => { live = false; };
  }, [d.id, cid, d.reload]);
  const c = ov.clusters.find((x) => x.id === cid)!;
  const at = ov.clusters.findIndex((x) => x.id === cid);
  const layer = ov.layers.find((l) => l.level === c.level)?.name;
  const stories = d.stories?.stories.filter((s) => s.board === cid) ?? [];
  const name = (id: string) => ov.clusters.find((x) => x.id === id)?.name ?? id;
  const step = (by: 1 | -1) => {
    const to = stepCluster(ov, cid, by), label = `${by < 0 ? "Previous" : "Next"} part: ${name(to)}`;
    return <Link className="bd-ibtn ws-step-btn" to={ws.link(ws.item({ kind: "cluster", cid: to }))} title={label} aria-label={label}>
      {by < 0 ? "‹" : "›"}</Link>;
  };
  const open = ws.addr.open && "node" in ws.addr.open ? ws.addr.open.node : null;
  return (
    <div className="ws-page graph">
      <div className="ws-story-bar">
        <header className="ws-story-head">
          <div className="ws-story-title">
            <h2>{c.risk && <span className={`bd-pill ${c.risk}`}>{c.risk}</span>}{c.name}</h2>
            <span className="ws-pos">{step(-1)}<span>{at + 1} of {ov.clusters.length}</span>{step(1)}</span>
          </div>
          <p className="ws-story-meta"><span className="muted">{layer ? `${layer} · ` : ""}{c.files.length} files · {c.changed} changed ·{" "}
            {c.flows} flows · {c.findings} finding{c.findings === 1 ? "" : "s"}</span>
            {stories.map((s) => (
              <Link key={s.id} className="ws-chip" to={ws.link(ws.item({ kind: "story", sid: s.id, view: "steps" }))}
                    title={`Go to story ${s.id}: ${short(s.title)}`} aria-label={`Go to story ${s.id}: ${short(s.title)}`}>
                <Ticks text={short(s.title, 32)} /> {s.id}</Link>
            ))}</p>
        </header>
      </div>
      {error ? <div className="ws-page"><div className="banner warn">{error}</div></div>
        : !board ? <p className="muted ws-page">Loading {c.name}…</p>
        : <GraphView key={cid} board={board} prefKey={`${d.id}.${cid}`} flowIndex={pickFlow(board.flows, ws.addr.flow, open)}
                     onFlow={(i) => ws.go({ ...ws.addr, flow: i + 1 }, true)} homeName={name}
                     onHome={(home, node) => ws.go({ ...ws.item({ kind: "cluster", cid: home }), open: { node }, tab: "diff" })} />}
    </div>
  );
}
