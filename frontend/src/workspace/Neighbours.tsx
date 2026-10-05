import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Neighbour, type Neighbours as Model } from "../api";
import { useWs } from "./context";

const LIMIT = 20;
const MAX = 500;                                             // the server lists at most this many of a side

const fileName = (path: string) => path.slice(path.lastIndexOf("/") + 1);

/** The Neighbours tab (spec 2026-10-04-review-workspace §3.7): callers, the node, callees; a row moves the panel to that
 * node (a history entry, so Back returns). Replaces growing the board on "+N callers". */
export default function Neighbours({ nid }: { nid: string }) {
  const ws = useWs(), d = ws.data;
  const [more, setMore] = useState<{ callers?: number; callees?: number }>({});    // a column grown by Show all
  const [model, setModel] = useState<Model | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setError(null);
    api.neighbours(d.id, nid, LIMIT, more).then((m) => { if (live) setModel(m); })
      .catch((e) => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [d.id, nid, more, tick]);
  if (error) return <div className="bd-note error">{error} <button className="bd-ibtn" onClick={() => setTick((t) => t + 1)}>Retry</button></div>;
  if (!model) return <div className="bd-note">Finding callers and callees…</div>;
  const row = (n: Neighbour) => {
    const where = n.path ? fileName(n.path) : null;
    return (
      <li key={n.id}>
        <Link to={ws.link(ws.opened({ node: n.id }, "neighbours"))} className={`ws-nb${n.test ? " test" : ""}`}
              title={`Open ${n.label}'s neighbours`} aria-label={`Open ${n.label}'s neighbours`}>
          <span className="ws-row-top"><b className="mono">{n.label}</b>
            {n.changed && <span className="ws-badge changed">changed</span>}
            {n.test && <span className="ws-badge">test</span>}
            {n.story && <span className="ws-handle">{n.story}</span>}</span>
          {where && <span className="ws-row-sub mono">{where}{n.line ? `:${n.line}` : ""}</span>}
        </Link>
      </li>
    );
  };
  const column = (title: string, key: "callers" | "callees") => {
    const side = model[key], all = Math.min(side.total, MAX);
    return (
      <section className="ws-nb-col" aria-label={title}>
        <h3>{title} <span className="muted small">{side.total}</span></h3>
        {side.items.length ? <ul>{side.items.map(row)}</ul> : <p className="muted small">None.</p>}
        {all > side.items.length && (
          <button className="link small" onClick={() => setMore((m) => ({ ...m, [key]: all }))}>
            {all === side.total ? `Show all ${side.total}` : `Show ${MAX} of ${side.total}`}</button>
        )}
      </section>
    );
  };
  return (
    <div className="ws-nbs">
      {column("Callers", "callers")}
      <section className="ws-nb-col me" aria-label="This function">
        <h3>This function</h3>
        <div className="ws-nb on"><b className="mono">{model.node.label}</b>
          {model.node.changed && <span className="ws-badge changed">changed</span>}
          {model.node.path && <span className="ws-row-sub mono">{fileName(model.node.path)}</span>}</div>
      </section>
      {column("Callees", "callees")}
    </div>
  );
}
